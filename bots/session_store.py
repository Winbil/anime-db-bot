from __future__ import annotations

import os
import time
from collections.abc import Iterator, MutableMapping
from typing import Generic, TypeVar

T = TypeVar("T")


def session_ttl_seconds() -> int:
    raw = os.getenv("TELEGRAM_SESSION_TTL_SECONDS", "3600").strip()
    try:
        return max(60, int(raw))
    except ValueError:
        return 3600


class ExpiringSessionStore(MutableMapping[str, T], Generic[T]):
    """Small dict-like TTL store for callback state kept in bot RAM."""

    def __init__(
        self,
        *,
        max_entries: int,
        ttl_seconds: int | None = None,
    ) -> None:
        self._max_entries = max(1, int(max_entries))
        self._ttl_seconds = max(1, int(ttl_seconds or session_ttl_seconds()))
        self._items: dict[str, tuple[float, T]] = {}

    def _prune(self) -> None:
        now = time.monotonic()
        expired = [
            key
            for key, (expires_at, _) in self._items.items()
            if expires_at <= now
        ]
        for key in expired:
            self._items.pop(key, None)

    def __getitem__(self, key: str) -> T:
        self._prune()
        expires_at, value = self._items[key]
        if expires_at <= time.monotonic():
            self._items.pop(key, None)
            raise KeyError(key)
        return value

    def __setitem__(self, key: str, value: T) -> None:
        self._prune()
        self._items.pop(key, None)
        self._items[key] = (time.monotonic() + self._ttl_seconds, value)
        while len(self._items) > self._max_entries:
            self._items.pop(next(iter(self._items)), None)

    def __delitem__(self, key: str) -> None:
        del self._items[key]

    def __iter__(self) -> Iterator[str]:
        self._prune()
        return iter(tuple(self._items))

    def __len__(self) -> int:
        self._prune()
        return len(self._items)

    def get(self, key: str, default: T | None = None) -> T | None:
        try:
            return self[key]
        except KeyError:
            return default

    def refresh(self, key: str) -> bool:
        """Extend one live session without changing its value."""
        try:
            value = self[key]
        except KeyError:
            return False
        self[key] = value
        return True
