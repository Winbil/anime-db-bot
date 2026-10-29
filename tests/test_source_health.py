from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, patch

from core.identity import AnimeIdentity
from core.source_errors import SourceCircuitOpen, SourceUnavailable
from services.runtime.source_health import SourceHealthRegistry
from sources.runtime.resilient import (
    resilient_episode_source,
    resilient_search_provider,
    resilient_source,
    resilient_trailer_source,
)


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


class _FailingSearchProvider:
    name = "MyAnimeList"

    async def search(self, query: str, *, page: int, limit: int):
        raise SourceUnavailable(
            "temporary search outage",
            source="mal",
            operation="search",
            transient=True,
        )


class _FailingTrailerSource:
    name = "Jikan"
    display_name = "MAL / Jikan"
    source_key = "mal"
    backend_key = "jikan"

    async def load_trailers(self, identity: AnimeIdentity):
        raise SourceUnavailable(
            "temporary trailer outage",
            source="jikan",
            operation="trailers",
            transient=True,
        )


class _FailingEpisodeSource:
    name = "Jikan"
    display_name = "MAL / Jikan"
    source_key = "mal"
    backend_key = "jikan"

    async def load_episode_page(self, identity: AnimeIdentity, *, page: int = 1):
        raise SourceUnavailable(
            "temporary episode outage",
            source="jikan",
            operation="episodes",
            transient=True,
        )

    async def load_episode(self, identity: AnimeIdentity, episode_number: int):
        raise SourceUnavailable(
            "temporary episode outage",
            source="jikan",
            operation="episode",
            transient=True,
        )


class SourceHealthTests(unittest.IsolatedAsyncioTestCase):
    async def test_three_final_transient_failures_open_circuit(self) -> None:
        health = SourceHealthRegistry(failure_threshold=3, cooldown_seconds=30)
        source = resilient_source(_FailingSource(), health)

        with patch("sources.runtime.resilient.asyncio.sleep", new=AsyncMock()):
            for _ in range(3):
                with self.assertRaises(SourceUnavailable):
                    await source.get_details(AnimeIdentity({"mal": "1"}))

        snapshot = health.snapshot("health")
        self.assertEqual(snapshot.consecutive_failures, 3)
        self.assertTrue(snapshot.circuit_open)
        with self.assertRaises(SourceCircuitOpen):
            await source.get_details(AnimeIdentity({"mal": "1"}))

    async def test_search_provider_uses_shared_source_circuit(self) -> None:
        health = SourceHealthRegistry(failure_threshold=1, cooldown_seconds=30)
        provider = resilient_search_provider(
            _FailingSearchProvider(),
            health,
            health_key="mal",
        )

        with patch("sources.runtime.resilient.asyncio.sleep", new=AsyncMock()):
            with self.assertRaises(SourceUnavailable):
                await provider.search("test", page=1, limit=10)

        self.assertTrue(health.snapshot("mal").circuit_open)
        with self.assertRaises(SourceCircuitOpen):
            await provider.search("test", page=1, limit=10)

    async def test_trailer_backend_uses_backend_health_key(self) -> None:
        health = SourceHealthRegistry(failure_threshold=1, cooldown_seconds=30)
        source = resilient_trailer_source(_FailingTrailerSource(), health)

        with patch("sources.runtime.resilient.asyncio.sleep", new=AsyncMock()):
            with self.assertRaises(SourceUnavailable):
                await source.load_trailers(AnimeIdentity({"mal": "1"}))

        self.assertTrue(health.snapshot("jikan").circuit_open)
        self.assertFalse(health.snapshot("mal").circuit_open)

    async def test_episode_backend_uses_backend_health_key(self) -> None:
        health = SourceHealthRegistry(failure_threshold=1, cooldown_seconds=30)
        source = resilient_episode_source(_FailingEpisodeSource(), health)

        with patch("sources.runtime.resilient.asyncio.sleep", new=AsyncMock()):
            with self.assertRaises(SourceUnavailable):
                await source.load_episode_page(AnimeIdentity({"mal": "1"}), page=1)

        self.assertTrue(health.snapshot("jikan").circuit_open)
        with self.assertRaises(SourceCircuitOpen):
            await source.load_episode(AnimeIdentity({"mal": "1"}), 1)

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
