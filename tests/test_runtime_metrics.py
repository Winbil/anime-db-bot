from __future__ import annotations

import unittest

from core.cache import BoundedTTLCache
from core.runtime_metrics import RuntimeMetricsRegistry, activate_runtime_metrics


class _Clock:
    def __init__(self, now: float = 0.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class RuntimeMetricsTests(unittest.TestCase):
    def test_rolling_windows_keep_recent_updates_and_source_calls(self) -> None:
        clock = _Clock(100.0)
        metrics = RuntimeMetricsRegistry(clock=clock)
        metrics.record_update(outcome="success")
        metrics.record_source_call("anilist", outcome="success", duration_ms=120.0)

        clock.advance(2 * 3600)
        metrics.record_update(outcome="error")
        metrics.record_source_call("anilist", outcome="error", duration_ms=300.0)
        metrics.record_source_call("trace_moe", outcome="limited", duration_ms=25.0)

        one_hour = metrics.window(3600)
        five_hours = metrics.window(5 * 3600)
        self.assertEqual(one_hour.updates, 1)
        self.assertEqual(one_hour.update_errors, 1)
        self.assertEqual(one_hour.source_calls, 2)
        self.assertEqual(one_hour.source_errors, 1)
        self.assertEqual(five_hours.updates, 2)
        self.assertEqual(five_hours.source_calls, 3)

        source_one_hour = metrics.source_window("AniList", 3600)
        source_five_hours = metrics.source_window("anilist", 5 * 3600)
        self.assertEqual(source_one_hour.calls, 1)
        self.assertEqual(source_one_hour.errors, 1)
        self.assertEqual(source_one_hour.average_latency_ms, 300.0)
        self.assertEqual(source_five_hours.calls, 2)
        self.assertEqual(source_five_hours.errors, 1)
        self.assertEqual(source_five_hours.average_latency_ms, 210.0)
        trace = metrics.source_window("trace_moe", 3600)
        self.assertEqual(trace.calls, 1)
        self.assertEqual(trace.errors, 0)
        self.assertEqual(trace.limited, 1)

    def test_cache_accesses_are_recorded_through_active_context(self) -> None:
        metrics_clock = _Clock(100.0)
        cache_clock = _Clock(100.0)
        metrics = RuntimeMetricsRegistry(clock=metrics_clock)
        cache = BoundedTTLCache[str, str](
            max_entries=2,
            ttl_seconds=10,
            clock=cache_clock,
            name="test_cache",
        )
        cache.set("hit", "value")
        cache.set("expired", "old", ttl_seconds=1)

        with activate_runtime_metrics(metrics):
            self.assertEqual(cache.get("hit"), "value")
            self.assertIsNone(cache.get("missing"))
            cache_clock.advance(2)
            self.assertIsNone(cache.get("expired"))

        window = metrics.window(3600)
        self.assertEqual(window.cache_hits, 1)
        self.assertEqual(window.cache_misses, 1)
        self.assertEqual(window.cache_expired, 1)
        self.assertAlmostEqual(window.cache_hit_rate or 0.0, 1 / 3)

        totals = metrics.cache_totals()
        self.assertEqual(len(totals), 1)
        self.assertEqual(totals[0].name, "test_cache")
        self.assertEqual(totals[0].accesses, 3)
        rolling = metrics.cache_window(86400)
        self.assertEqual(rolling[0].name, "test_cache")
        self.assertEqual(rolling[0].accesses, 3)

    def test_metrics_are_bounded_to_24_hours(self) -> None:
        clock = _Clock(0.0)
        metrics = RuntimeMetricsRegistry(clock=clock)
        metrics.record_update(outcome="success")
        clock.advance(25 * 3600)
        metrics.record_update(outcome="success")

        day = metrics.window(24 * 3600)
        self.assertEqual(day.updates, 1)
        self.assertGreaterEqual(metrics.uptime_seconds, 25 * 3600)


if __name__ == "__main__":
    unittest.main()
