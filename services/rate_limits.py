from __future__ import annotations

import asyncio
import math
import os
import re
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RateLimitDecision:
    allowed: bool
    retry_after: int = 0
    window: str | None = None


class PersonalRateLimiter:
    """Sliding-window limiter keyed strictly by ``(platform, user_id)``."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._events: dict[tuple[str, int], deque[float]] = defaultdict(deque)

    @staticmethod
    def _positive_int(name: str, default: int) -> int:
        raw = os.getenv(name, str(default)).strip()
        try:
            return max(1, int(raw))
        except ValueError:
            return default

    @property
    def per_minute(self) -> int:
        return self._positive_int("USER_RATE_LIMIT_PER_MINUTE", 50)

    @property
    def per_hour(self) -> int:
        return self._positive_int("USER_RATE_LIMIT_PER_HOUR", 1000)

    def check(
        self,
        platform: str,
        user_id: int,
        *,
        now: float | None = None,
    ) -> RateLimitDecision:
        timestamp = time.monotonic() if now is None else float(now)
        key = ((platform or "").strip().casefold(), int(user_id))

        with self._lock:
            events = self._events[key]
            hour_floor = timestamp - 3600.0
            while events and events[0] <= hour_floor:
                events.popleft()

            minute_floor = timestamp - 60.0
            minute_events = 0
            first_minute_event: float | None = None
            for event_at in events:
                if event_at > minute_floor:
                    minute_events += 1
                    if first_minute_event is None:
                        first_minute_event = event_at

            if minute_events >= self.per_minute and first_minute_event is not None:
                retry_after = max(1, math.ceil(first_minute_event + 60.0 - timestamp))
                return RateLimitDecision(False, retry_after, "minute")

            if len(events) >= self.per_hour:
                retry_after = max(1, math.ceil(events[0] + 3600.0 - timestamp))
                return RateLimitDecision(False, retry_after, "hour")

            events.append(timestamp)
            return RateLimitDecision(True)

    def reset(self) -> None:
        with self._lock:
            self._events.clear()


_ENV_TOKEN_RE = re.compile(r"[^A-Z0-9]+")


def _env_token(value: str) -> str:
    return _ENV_TOKEN_RE.sub("_", (value or "").strip().upper()).strip("_")


def _configured_positive_int(name: str) -> int | None:
    raw = os.getenv(name, "").strip()
    if not raw:
        return None
    try:
        return max(1, int(raw))
    except ValueError:
        return None


def _source_limit(source: str) -> int:
    source_token = _env_token(source)
    configured = _configured_positive_int(
        f"UPSTREAM_RATE_LIMIT_{source_token}_PER_MINUTE"
    )
    if configured is not None:
        return configured

    default_configured = _configured_positive_int(
        "UPSTREAM_RATE_LIMIT_DEFAULT_PER_MINUTE"
    )
    if default_configured is not None:
        return default_configured

    defaults = {
        "ANILIST": 80,
        "SHIKIMORI": 240,
        "MAL": 120,
        "MYANIMELIST": 120,
        "JIKAN": 30,
    }
    return defaults.get(source_token, 120)


def _operation_limit(source: str, operation: str) -> int | None:
    source_token = _env_token(source)
    operation_token = _env_token(operation)
    configured = _configured_positive_int(
        f"UPSTREAM_RATE_LIMIT_{source_token}_{operation_token}_PER_MINUTE"
    )
    if configured is not None:
        return configured

    # Multi-request logical operations are intentionally more conservative.
    defaults = {
        ("ANILIST", "PEOPLE"): 20,
        ("SHIKIMORI", "PEOPLE"): 60,
        ("JIKAN", "METADATA"): 20,
        ("JIKAN", "PEOPLE"): 15,
        ("JIKAN", "EPISODES"): 20,
    }
    return defaults.get((source_token, operation_token))


class UpstreamRateLimiter:
    """Async source-global + optional endpoint sliding-window safety limiter.

    Unlike the personal limiter, this layer waits instead of blaming/rejecting a
    user. Every operation first consumes the source-global bucket, so endpoint
    buckets can only make a path stricter and can never exceed the source quota.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._events: dict[tuple[str, ...], deque[float]] = defaultdict(deque)

    async def _acquire_bucket(self, key: tuple[str, ...], limit: int) -> None:
        while True:
            now = time.monotonic()
            with self._lock:
                events = self._events[key]
                floor = now - 60.0
                while events and events[0] <= floor:
                    events.popleft()

                if len(events) < limit:
                    events.append(now)
                    return

                wait_for = max(0.01, events[0] + 60.0 - now)

            await asyncio.sleep(wait_for)

    async def acquire(self, source: str, operation: str = "default") -> None:
        source_key = (source or "unknown").strip().casefold()
        operation_key = (operation or "default").strip().casefold()

        await self._acquire_bucket(
            ("source", source_key),
            _source_limit(source_key),
        )

        operation_limit = _operation_limit(source_key, operation_key)
        if operation_limit is not None:
            await self._acquire_bucket(
                ("operation", source_key, operation_key),
                operation_limit,
            )

    def reset(self) -> None:
        with self._lock:
            self._events.clear()


PERSONAL_RATE_LIMITER = PersonalRateLimiter()
UPSTREAM_RATE_LIMITER = UpstreamRateLimiter()


async def wait_for_upstream(source: str, operation: str = "default") -> None:
    await UPSTREAM_RATE_LIMITER.acquire(source, operation)


def reset_rate_limits() -> None:
    PERSONAL_RATE_LIMITER.reset()
    UPSTREAM_RATE_LIMITER.reset()
