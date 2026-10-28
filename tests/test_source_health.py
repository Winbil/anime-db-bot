from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, patch

from core.identity import AnimeIdentity
from core.source_errors import SourceCircuitOpen, SourceUnavailable
from services.source_health import SourceHealthRegistry
from sources.resilient import resilient_source


class _FailingSource:
    name = "HealthSource"
    source_key = "health"

    async def get_details(self, identity: AnimeIdentity):
        raise SourceUnavailable(
            "temporary outage",
            source="health",
            operation="metadata",
            transient=True,
        )


class SourceHealthTests(unittest.IsolatedAsyncioTestCase):
    async def test_three_final_transient_failures_open_circuit(self) -> None:
        health = SourceHealthRegistry(failure_threshold=3, cooldown_seconds=30)
        source = resilient_source(_FailingSource(), health)

        with patch("sources.resilient.asyncio.sleep", new=AsyncMock()):
            for _ in range(3):
                with self.assertRaises(SourceUnavailable):
                    await source.get_details(AnimeIdentity({"mal": "1"}))

        snapshot = health.snapshot("health")
        self.assertEqual(snapshot.consecutive_failures, 3)
        self.assertTrue(snapshot.circuit_open)
        with self.assertRaises(SourceCircuitOpen):
            await source.get_details(AnimeIdentity({"mal": "1"}))

    def test_success_resets_transient_failure_state(self) -> None:
        health = SourceHealthRegistry(failure_threshold=3, cooldown_seconds=30)
        error = SourceUnavailable(
            "temporary",
            source="health",
            operation="metadata",
            transient=True,
        )
        health.record_failure("health", error)
        health.record_failure("health", error)
        self.assertEqual(health.snapshot("health").consecutive_failures, 2)
        health.record_success("health")
        snapshot = health.snapshot("health")
        self.assertEqual(snapshot.consecutive_failures, 0)
        self.assertFalse(snapshot.circuit_open)
        self.assertIsNone(snapshot.last_error)

    def test_non_transient_failure_does_not_trip_circuit(self) -> None:
        health = SourceHealthRegistry(failure_threshold=1, cooldown_seconds=30)
        health.record_failure(
            "health",
            SourceUnavailable(
                "permanent",
                source="health",
                operation="metadata",
                transient=False,
            ),
        )
        self.assertFalse(health.snapshot("health").circuit_open)


if __name__ == "__main__":
    unittest.main()
