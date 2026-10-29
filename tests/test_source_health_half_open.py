from __future__ import annotations

import asyncio
import unittest

from core.identity import AnimeIdentity
from core.source_errors import SourceCircuitOpen, SourceUnavailable
from services.runtime.source_health import SourceHealthRegistry
from sources.runtime.resilient import resilient_source


class _Clock:
    def __init__(self, now: float = 100.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now


class _SwitchableSource:
    name = "ProbeSource"
    source_key = "probe"

    def __init__(self) -> None:
        self.calls = 0
        self.fail = True
        self.started: asyncio.Event | None = None
        self.release: asyncio.Event | None = None

    async def get_details(self, identity: AnimeIdentity):
        self.calls += 1
        if self.started is not None:
            self.started.set()
        if self.release is not None:
            await self.release.wait()
        if self.fail:
            raise SourceUnavailable(
                "temporary outage",
                source="probe",
                operation="metadata",
                transient=True,
            )
        return None


def _open_registry(health: SourceHealthRegistry) -> None:
    error = SourceUnavailable(
        "temporary outage",
        source="probe",
        operation="metadata",
        transient=True,
    )
    for _ in range(health.failure_threshold):
        health.record_failure("probe", error)


class SourceHealthHalfOpenTests(unittest.IsolatedAsyncioTestCase):
    async def test_cooldown_allows_exactly_one_single_attempt_probe(self) -> None:
        clock = _Clock()
        health = SourceHealthRegistry(
            failure_threshold=3,
            cooldown_seconds=10,
            clock=clock,
        )
        raw = _SwitchableSource()
        source = resilient_source(raw, health)
        _open_registry(health)
        clock.now = health.snapshot("probe").circuit_open_until + 1.0
        self.assertEqual(health.snapshot("probe").state, "half_open")

        raw.started = asyncio.Event()
        raw.release = asyncio.Event()
        probe = asyncio.create_task(source.get_details(AnimeIdentity({"mal": "1"})))
        await raw.started.wait()
        self.assertEqual(health.snapshot("probe").state, "half_open")
        with self.assertRaises(SourceCircuitOpen):
            await source.get_details(AnimeIdentity({"mal": "1"}))
        raw.release.set()
        with self.assertRaises(SourceUnavailable):
            await probe

        # One failed recovery probe must reopen immediately even though the
        # normal threshold is three failed application calls.
        self.assertEqual(raw.calls, 1)
        snapshot = health.snapshot("probe")
        self.assertEqual(snapshot.state, "open")
        self.assertGreaterEqual(snapshot.consecutive_failures, 3)

    async def test_successful_probe_closes_circuit(self) -> None:
        clock = _Clock()
        health = SourceHealthRegistry(
            failure_threshold=1,
            cooldown_seconds=10,
            clock=clock,
        )
        raw = _SwitchableSource()
        source = resilient_source(raw, health)
        _open_registry(health)
        clock.now = health.snapshot("probe").circuit_open_until + 1.0
        raw.fail = False

        self.assertIsNone(await source.get_details(AnimeIdentity({"mal": "1"})))

        snapshot = health.snapshot("probe")
        self.assertEqual(snapshot.state, "closed")
        self.assertEqual(snapshot.consecutive_failures, 0)
        self.assertIsNone(snapshot.last_error)

    async def test_cancelled_probe_is_released_for_next_recovery_check(self) -> None:
        clock = _Clock()
        health = SourceHealthRegistry(
            failure_threshold=1,
            cooldown_seconds=10,
            clock=clock,
        )
        raw = _SwitchableSource()
        source = resilient_source(raw, health)
        _open_registry(health)
        clock.now = health.snapshot("probe").circuit_open_until + 1.0
        raw.started = asyncio.Event()
        raw.release = asyncio.Event()

        probe = asyncio.create_task(source.get_details(AnimeIdentity({"mal": "1"})))
        await raw.started.wait()
        probe.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await probe
        self.assertFalse(health.snapshot("probe").probe_in_flight)

        raw.started = None
        raw.release = None
        raw.fail = False
        self.assertIsNone(await source.get_details(AnimeIdentity({"mal": "1"})))
        self.assertEqual(health.snapshot("probe").state, "closed")


if __name__ == "__main__":
    unittest.main()
