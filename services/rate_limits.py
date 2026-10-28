from __future__ import annotations

import asyncio
import math
import threading
import time
from collections import defaultdict, deque
from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass
from functools import lru_cache
from typing import Iterator

from core.settings import RateLimitSettings, get_settings


@dataclass(frozen=True, slots=True)
class RateLimitDecision:
    allowed: bool
    retry_after: int = 0
    window: str | None = None


def _runtime_rate_settings() -> RateLimitSettings:
    return get_settings().rate_limits


class PersonalRateLimiter:
    """Sliding-window limiter keyed strictly by ``(platform, user_id)``."""

    def __init__(self, settings: RateLimitSettings | None = None) -> None:
        self._settings = settings
        self._lock = threading.RLock()
        self._events: dict[tuple[str, int], deque[float]] = defaultdict(deque)

    @property
    def settings(self) -> RateLimitSettings:
        return self._settings or _runtime_rate_settings()

    @property
    def per_minute(self) -> int:
        return self.settings.user_per_minute

    @property
    def per_hour(self) -> int:
        return self.settings.user_per_hour

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


class UpstreamRateLimiter:
    """Async source-global + optional endpoint sliding-window safety limiter."""

    def __init__(self, settings: RateLimitSettings | None = None) -> None:
        self._settings = settings
        self._lock = threading.RLock()
        self._events: dict[tuple[str, ...], deque[float]] = defaultdict(deque)

    @property
    def settings(self) -> RateLimitSettings:
        return self._settings or _runtime_rate_settings()

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
            self.settings.source_limit(source_key),
        )

        operation_limit = self.settings.operation_limit(source_key, operation_key)
        if operation_limit is not None:
            await self._acquire_bucket(
                ("operation", source_key, operation_key),
                operation_limit,
            )

    def reset(self) -> None:
        with self._lock:
            self._events.clear()


_CURRENT_PERSONAL_RATE_LIMITER: ContextVar[PersonalRateLimiter | None] = ContextVar(
    "anime_db_bot_personal_rate_limiter",
    default=None,
)
_CURRENT_UPSTREAM_RATE_LIMITER: ContextVar[UpstreamRateLimiter | None] = ContextVar(
    "anime_db_bot_upstream_rate_limiter",
    default=None,
)


@lru_cache(maxsize=1)
def _default_personal_rate_limiter() -> PersonalRateLimiter:
    return PersonalRateLimiter(get_settings().rate_limits)


@lru_cache(maxsize=1)
def _default_upstream_rate_limiter() -> UpstreamRateLimiter:
    return UpstreamRateLimiter(get_settings().rate_limits)


def get_personal_rate_limiter() -> PersonalRateLimiter:
    return _CURRENT_PERSONAL_RATE_LIMITER.get() or _default_personal_rate_limiter()


def get_upstream_rate_limiter() -> UpstreamRateLimiter:
    return _CURRENT_UPSTREAM_RATE_LIMITER.get() or _default_upstream_rate_limiter()


@contextmanager
def activate_rate_limiters(
    personal: PersonalRateLimiter,
    upstream: UpstreamRateLimiter,
) -> Iterator[tuple[PersonalRateLimiter, UpstreamRateLimiter]]:
    personal_token: Token[PersonalRateLimiter | None] = (
        _CURRENT_PERSONAL_RATE_LIMITER.set(personal)
    )
    upstream_token: Token[UpstreamRateLimiter | None] = (
        _CURRENT_UPSTREAM_RATE_LIMITER.set(upstream)
    )
    try:
        yield personal, upstream
    finally:
        _CURRENT_UPSTREAM_RATE_LIMITER.reset(upstream_token)
        _CURRENT_PERSONAL_RATE_LIMITER.reset(personal_token)


async def wait_for_upstream(source: str, operation: str = "default") -> None:
    await get_upstream_rate_limiter().acquire(source, operation)


def reset_rate_limits() -> None:
    get_personal_rate_limiter().reset()
    get_upstream_rate_limiter().reset()
