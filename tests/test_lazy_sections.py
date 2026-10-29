from __future__ import annotations

import unittest
from unittest.mock import AsyncMock

from core.identity import AnimeIdentity
from core.models import DescriptionDetails, PopularityStats
from services.media.sections import (
    DescriptionService,
    PopularityService,
    ScreenshotService,
)
from sources.providers.anilist import BY_ID_QUERY as ANILIST_BY_ID_QUERY
from sources.providers.anilist import DETAIL_QUERY as ANILIST_DETAIL_QUERY
from sources.providers.mal import DETAIL_FIELDS as MAL_DETAIL_FIELDS
from sources.providers.shikimori import DETAIL_FIELDS as SHIKIMORI_DETAIL_FIELDS


class _LazySource:
    name = "LazyDB"
    source_key = "shikimori"

    def __init__(self) -> None:
        self.load_screenshots = AsyncMock(return_value=["a", "b"])
        self.load_popularity = AsyncMock(return_value=PopularityStats(list_users=10))
        self.load_description = AsyncMock(
            return_value=DescriptionDetails(description="Long text", background="Extra")
        )


class LazySectionServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_sections_load_only_applicable_confirmed_identity_sources(
        self,
    ) -> None:
        source = _LazySource()
        identity = AnimeIdentity({"shikimori": "10"})

        screenshots = await ScreenshotService([source]).load(identity)
        popularity = await PopularityService([source]).load(identity)
        descriptions = await DescriptionService([source]).load(identity)

        self.assertEqual(screenshots.by_source, {"LazyDB": ["a", "b"]})
        self.assertEqual(popularity.by_source["LazyDB"].list_users, 10)
        self.assertEqual(descriptions.by_source["LazyDB"].description, "Long text")
        self.assertEqual(screenshots.key_by_source, {"LazyDB": "shikimori"})
        source.load_screenshots.assert_awaited_once()
        source.load_popularity.assert_awaited_once()
        source.load_description.assert_awaited_once()

    async def test_missing_identity_edge_skips_lazy_source(self) -> None:
        source = _LazySource()
        identity = AnimeIdentity({"mal": "20"})

        result = await ScreenshotService([source]).load(identity)

        self.assertEqual(result.by_source, {})
        source.load_screenshots.assert_not_awaited()


class InitialPayloadBoundaryTests(unittest.TestCase):
    def test_shikimori_initial_query_excludes_heavy_sections(self) -> None:
        self.assertNotIn("screenshots", SHIKIMORI_DETAIL_FIELDS)
        self.assertNotIn("description", SHIKIMORI_DETAIL_FIELDS)
        self.assertNotIn("statusesStats", SHIKIMORI_DETAIL_FIELDS)
        self.assertNotIn("scoresStats", SHIKIMORI_DETAIL_FIELDS)

    def test_anilist_initial_queries_exclude_heavy_sections(self) -> None:
        for query in (ANILIST_DETAIL_QUERY, ANILIST_BY_ID_QUERY):
            with self.subTest(query=query[:30]):
                self.assertNotIn("description", query)
                self.assertNotIn("popularity", query)
                self.assertNotIn("favourites", query)
                self.assertNotIn("rankings", query)
                self.assertNotIn("statusDistribution", query)
                self.assertNotIn("scoreDistribution", query)

    def test_mal_initial_fields_exclude_heavy_sections(self) -> None:
        for field in (
            "synopsis",
            "background",
            "rank",
            "popularity",
            "num_list_users",
            "num_scoring_users",
            "num_favorites",
            "statistics",
        ):
            with self.subTest(field=field):
                self.assertNotIn(field, MAL_DETAIL_FIELDS.split(","))


if __name__ == "__main__":
    unittest.main()
