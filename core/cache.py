from __future__ import annotations

import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Callable, Generic, TypeVar

K = TypeVar("K")
V = TypeVar("V")


@dataclass(slots=True)
class _Entry(Generic[V]):
    expires_at: float
    value: V


class BoundedTTLCache(Generic[K, V]):
    """Small fixed-TTL LRU cache for process-local data.

    Reads update LRU order but never extend the TTL. Expired entries are removed
    lazily, and insertion always enforces ``max_entries`` so a high-cardinality
    upstream cannot grow process memory without bound.
    """

    def __init__(
        self,
        *,
        max_entries: int,
        ttl_seconds: float | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.max_entries = max(1, int(max_entries))
        self.ttl_seconds = None if ttl_seconds is None else max(0.0, float(ttl_seconds))
        self._clock = clock
        self._items: OrderedDict[K, _Entry[V]] = OrderedDict()

    def _prune_expired(self, now: float | None = None) -> None:
        if not self._items:
            return
        timestamp = self._clock() if now is None else now
        expired = [
            key for key, entry in self._items.items() if entry.expires_at <= timestamp
        ]
        for key in expired:
            self._items.pop(key, None)

    def set(self, key: K, value: V, *, ttl_seconds: float | None = None) -> None:
        ttl = self.ttl_seconds if ttl_seconds is None else max(0.0, float(ttl_seconds))
        if ttl is None:
            raise ValueError("TTL must be configured on the cache or set() call")
        if ttl <= 0:
            self._items.pop(key, None)
            return

        now = self._clock()
        self._prune_expired(now)
        self._items[key] = _Entry(expires_at=now + ttl, value=value)
        self._items.move_to_end(key)
        while len(self._items) > self.max_entries:
            self._items.popitem(last=False)

    def get(self, key: K, default: V | None = None) -> V | None:
        try:
            return self[key]
        except KeyError:
            return default

    def __getitem__(self, key: K) -> V:
        entry = self._items.get(key)
        if entry is None:
            raise KeyError(key)
        if entry.expires_at <= self._clock():
            self._items.pop(key, None)
            raise KeyError(key)
        self._items.move_to_end(key)
        return entry.value

    def __contains__(self, key: object) -> bool:
        try:
            self[key]  # type: ignore[index]
        except (KeyError, TypeError):
            return False
        return True

    def pop(self, key: K, default: V | None = None) -> V | None:
        entry = self._items.pop(key, None)
        if entry is None or entry.expires_at <= self._clock():
            return default
        return entry.value

    def clear(self) -> None:
        self._items.clear()

    def __len__(self) -> int:
        self._prune_expired()
        return len(self._items)
