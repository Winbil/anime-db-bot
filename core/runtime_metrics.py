from __future__ import annotations

import time
from collections import deque
from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass, field
from threading import Lock
from typing import Callable, Iterator

_MAX_WINDOW_SECONDS = 24 * 60 * 60


@dataclass(frozen=True, slots=True)
class RuntimeSourceDescriptor:
    key: str
    display_name: str
    mode: str = "remote"
    note: str | None = None


@dataclass(frozen=True, slots=True)
class SourceWindowSnapshot:
    calls: int = 0
    errors: int = 0
    limited: int = 0
    latency_samples: int = 0
    latency_sum_ms: float = 0.0

    @property
    def average_latency_ms(self) -> float | None:
        if self.latency_samples <= 0:
            return None
        return self.latency_sum_ms / self.latency_samples


@dataclass(frozen=True, slots=True)
class RuntimeWindowSnapshot:
    updates: int = 0
    update_errors: int = 0
    source_calls: int = 0
    source_errors: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    cache_expired: int = 0

    @property
    def total_operations(self) -> int:
        return self.updates + self.source_calls

    @property
    def cache_accesses(self) -> int:
        return self.cache_hits + self.cache_misses + self.cache_expired

    @property
    def cache_hit_rate(self) -> float | None:
        if self.cache_accesses <= 0:
            return None
        return self.cache_hits / self.cache_accesses


@dataclass(frozen=True, slots=True)
class CacheMetricsSnapshot:
    name: str
    hits: int
    misses: int
    expired: int

    @property
    def accesses(self) -> int:
        return self.hits + self.misses + self.expired

    @property
    def hit_rate(self) -> float | None:
        if self.accesses <= 0:
            return None
        return self.hits / self.accesses


@dataclass(slots=True)
class _SourceBucket:
    calls: int = 0
    errors: int = 0
    limited: int = 0
    latency_samples: int = 0
    latency_sum_ms: float = 0.0


@dataclass(slots=True)
class _CacheBucket:
    hits: int = 0
    misses: int = 0
    expired: int = 0


@dataclass(slots=True)
class _MinuteBucket:
    minute: int
    updates: int = 0
    update_errors: int = 0
    source_calls: int = 0
    source_errors: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    cache_expired: int = 0
    sources: dict[str, _SourceBucket] = field(default_factory=dict)
    caches: dict[str, _CacheBucket] = field(default_factory=dict)


class RuntimeMetricsRegistry:
    """Process-local rolling telemetry for admin diagnostics.

    The registry stores minute buckets for at most 24 hours. It intentionally
    contains only counters, timings, normalized source/cache names and outcomes;
    request payloads, user IDs, queries and upstream error text are never stored.
    """

    def __init__(self, *, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._started_at = clock()
        self._buckets: deque[_MinuteBucket] = deque()
        self._cache_totals: dict[str, _CacheBucket] = {}
        self._lock = Lock()

    @staticmethod
    def _key(value: str, fallback: str) -> str:
        return (value or fallback).strip().casefold() or fallback

    def _bucket_locked(self, now: float) -> _MinuteBucket:
        minute = int(now // 60)
        cutoff = minute - (_MAX_WINDOW_SECONDS // 60) - 1
        while self._buckets and self._buckets[0].minute < cutoff:
            self._buckets.popleft()
        if not self._buckets or self._buckets[-1].minute != minute:
            self._buckets.append(_MinuteBucket(minute=minute))
        return self._buckets[-1]

    def record_update(self, *, outcome: str) -> None:
        now = self._clock()
        with self._lock:
            bucket = self._bucket_locked(now)
            bucket.updates += 1
            if outcome != "success":
                bucket.update_errors += 1

    def record_source_call(
        self,
        source: str,
        *,
        outcome: str,
        duration_ms: float | None = None,
    ) -> None:
        key = self._key(source, "unknown")
        now = self._clock()
        with self._lock:
            bucket = self._bucket_locked(now)
            bucket.source_calls += 1
            source_bucket = bucket.sources.setdefault(key, _SourceBucket())
            source_bucket.calls += 1
            if outcome == "error":
                bucket.source_errors += 1
                source_bucket.errors += 1
            elif outcome == "limited":
                source_bucket.limited += 1
            if duration_ms is not None and duration_ms >= 0:
                source_bucket.latency_samples += 1
                source_bucket.latency_sum_ms += float(duration_ms)

    def record_cache_access(self, cache: str, *, result: str) -> None:
        name = self._key(cache, "cache")
        now = self._clock()
        with self._lock:
            bucket = self._bucket_locked(now)
            rolling = bucket.caches.setdefault(name, _CacheBucket())
            total = self._cache_totals.setdefault(name, _CacheBucket())
            if result == "hit":
                bucket.cache_hits += 1
                rolling.hits += 1
                total.hits += 1
            elif result == "expired":
                bucket.cache_expired += 1
                rolling.expired += 1
                total.expired += 1
            else:
                bucket.cache_misses += 1
                rolling.misses += 1
                total.misses += 1

    def _selected_buckets_locked(self, seconds: int, now: float) -> list[_MinuteBucket]:
        seconds = min(_MAX_WINDOW_SECONDS, max(1, int(seconds)))
        cutoff_minute = int(max(0.0, now - seconds) // 60)
        self._bucket_locked(now)
        return [bucket for bucket in self._buckets if bucket.minute >= cutoff_minute]

    def window(self, seconds: int) -> RuntimeWindowSnapshot:
        now = self._clock()
        with self._lock:
            buckets = self._selected_buckets_locked(seconds, now)
            return RuntimeWindowSnapshot(
                updates=sum(bucket.updates for bucket in buckets),
                update_errors=sum(bucket.update_errors for bucket in buckets),
                source_calls=sum(bucket.source_calls for bucket in buckets),
                source_errors=sum(bucket.source_errors for bucket in buckets),
                cache_hits=sum(bucket.cache_hits for bucket in buckets),
                cache_misses=sum(bucket.cache_misses for bucket in buckets),
                cache_expired=sum(bucket.cache_expired for bucket in buckets),
            )

    def source_window(self, source: str, seconds: int) -> SourceWindowSnapshot:
        key = self._key(source, "unknown")
        now = self._clock()
        with self._lock:
            buckets = self._selected_buckets_locked(seconds, now)
            values = [bucket.sources.get(key) for bucket in buckets]
            return SourceWindowSnapshot(
                calls=sum(value.calls for value in values if value is not None),
                errors=sum(value.errors for value in values if value is not None),
                limited=sum(value.limited for value in values if value is not None),
                latency_samples=sum(
                    value.latency_samples for value in values if value is not None
                ),
                latency_sum_ms=sum(
                    value.latency_sum_ms for value in values if value is not None
                ),
            )

    def cache_totals(self) -> tuple[CacheMetricsSnapshot, ...]:
        with self._lock:
            values = [
                CacheMetricsSnapshot(name, item.hits, item.misses, item.expired)
                for name, item in self._cache_totals.items()
            ]
        values.sort(key=lambda item: (-item.accesses, item.name))
        return tuple(values)

    def cache_window(self, seconds: int) -> tuple[CacheMetricsSnapshot, ...]:
        now = self._clock()
        with self._lock:
            buckets = self._selected_buckets_locked(seconds, now)
            names = {name for bucket in buckets for name in bucket.caches}
            values = []
            for name in names:
                samples = [bucket.caches.get(name) for bucket in buckets]
                values.append(
                    CacheMetricsSnapshot(
                        name=name,
                        hits=sum(item.hits for item in samples if item is not None),
                        misses=sum(item.misses for item in samples if item is not None),
                        expired=sum(
                            item.expired for item in samples if item is not None
                        ),
                    )
                )
        values.sort(key=lambda item: (-item.accesses, item.name))
        return tuple(values)

    @property
    def uptime_seconds(self) -> float:
        return max(0.0, self._clock() - self._started_at)


_CURRENT_RUNTIME_METRICS: ContextVar[RuntimeMetricsRegistry | None] = ContextVar(
    "anime_db_bot_runtime_metrics",
    default=None,
)


def get_runtime_metrics() -> RuntimeMetricsRegistry | None:
    return _CURRENT_RUNTIME_METRICS.get()


@contextmanager
def activate_runtime_metrics(
    registry: RuntimeMetricsRegistry,
) -> Iterator[RuntimeMetricsRegistry]:
    token: Token[RuntimeMetricsRegistry | None] = _CURRENT_RUNTIME_METRICS.set(registry)
    try:
        yield registry
    finally:
        _CURRENT_RUNTIME_METRICS.reset(token)


def record_cache_access(cache: str, result: str) -> None:
    registry = get_runtime_metrics()
    if registry is not None:
        registry.record_cache_access(cache, result=result)
