from __future__ import annotations

import unittest

from core.cache import BoundedTTLCache


class _Clock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now


class BoundedTTLCacheTests(unittest.TestCase):
    def test_expiry_does_not_slide_on_read(self) -> None:
        clock = _Clock()
        cache = BoundedTTLCache[str, str](max_entries=2, ttl_seconds=10, clock=clock)
        cache.set("a", "value")
        clock.now = 109
        self.assertEqual(cache["a"], "value")
        clock.now = 111
        with self.assertRaises(KeyError):
            _ = cache["a"]
        self.assertEqual(len(cache), 0)

    def test_lru_eviction_is_bounded(self) -> None:
        clock = _Clock()
        cache = BoundedTTLCache[str, int](max_entries=2, ttl_seconds=60, clock=clock)
        cache.set("a", 1)
        cache.set("b", 2)
        self.assertEqual(cache["a"], 1)  # a becomes most recently used
        cache.set("c", 3)
        self.assertIn("a", cache)
        self.assertNotIn("b", cache)
        self.assertIn("c", cache)
        self.assertEqual(len(cache), 2)

    def test_per_entry_ttl_and_cached_none(self) -> None:
        clock = _Clock()
        cache = BoundedTTLCache[str, str | None](max_entries=3, clock=clock)
        cache.set("negative", None, ttl_seconds=5)
        cache.set("positive", "x", ttl_seconds=20)
        self.assertIn("negative", cache)
        self.assertIsNone(cache["negative"])
        clock.now += 6
        self.assertNotIn("negative", cache)
        self.assertEqual(cache["positive"], "x")

    def test_zero_ttl_does_not_store(self) -> None:
        cache = BoundedTTLCache[str, str](max_entries=2, ttl_seconds=0)
        cache.set("a", "x")
        self.assertNotIn("a", cache)


if __name__ == "__main__":
    unittest.main()
