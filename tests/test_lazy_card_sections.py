from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from bots.telegram.card.features.descriptions import ensure_descriptions_loaded
from bots.telegram.card.features.popularity import ensure_popularity_loaded
from bots.telegram.card.features.screenshots import ensure_screenshots_loaded
from bots.telegram.card.runtime.state import AnimeCardSession
from core.models import AggregatedAnime, DescriptionDetails, PopularityStats
from services.media.sections import LazySectionLoadResult


class LazyCardSectionTests(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def _session() -> AnimeCardSession:
        return AnimeCardSession(
            anime=AggregatedAnime(
                title="Test",
                external_ids={"anilist": "10"},
                sources=["AniList"],
            ),
            owner_user_id=1,
        )

    async def test_screenshots_load_once_into_session_anime(self) -> None:
        session = self._session()
        service = SimpleNamespace(
            load=AsyncMock(
                return_value=LazySectionLoadResult(
                    by_source={"Shikimori": ["https://example.invalid/1.jpg"]}
                )
            )
        )
        context = SimpleNamespace(screenshot_service=service)
        message = AsyncMock()
        with patch(
            "bots.telegram.card.features.screenshots.get_app_context",
            return_value=context,
        ):
            await ensure_screenshots_loaded(message, session, locale="en")
            await ensure_screenshots_loaded(message, session, locale="en")

        self.assertTrue(session.screenshots_loaded)
        self.assertEqual(
            session.anime.screenshots_by_source,
            {"Shikimori": ["https://example.invalid/1.jpg"]},
        )
        service.load.assert_awaited_once()

    async def test_popularity_load_once_into_source_scoped_mapping(self) -> None:
        session = self._session()
        service = SimpleNamespace(
            load=AsyncMock(
                return_value=LazySectionLoadResult(
                    by_source={"AniList": PopularityStats(list_users=50)}
                )
            )
        )
        context = SimpleNamespace(popularity_service=service)
        message = AsyncMock()
        with patch(
            "bots.telegram.card.features.popularity.get_app_context",
            return_value=context,
        ):
            await ensure_popularity_loaded(message, session, locale="en")
            await ensure_popularity_loaded(message, session, locale="en")

        self.assertTrue(session.popularity_loaded)
        self.assertEqual(session.anime.popularity_by_source["AniList"].list_users, 50)
        service.load.assert_awaited_once()

    async def test_descriptions_keep_background_provenance(self) -> None:
        session = self._session()
        service = SimpleNamespace(
            load=AsyncMock(
                return_value=LazySectionLoadResult(
                    by_source={
                        "MyAnimeList": DescriptionDetails(
                            description="Synopsis",
                            background="Background",
                        )
                    }
                )
            )
        )
        context = SimpleNamespace(description_service=service)
        message = AsyncMock()
        with patch(
            "bots.telegram.card.features.descriptions.get_app_context",
            return_value=context,
        ):
            await ensure_descriptions_loaded(message, session, locale="en")
            await ensure_descriptions_loaded(message, session, locale="en")

        self.assertTrue(session.descriptions_loaded)
        self.assertEqual(session.anime.descriptions, {"MyAnimeList": "Synopsis"})
        self.assertEqual(
            session.anime.backgrounds_by_source,
            {"MyAnimeList": "Background"},
        )
        service.load.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
