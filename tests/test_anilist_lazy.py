from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, patch

from core.identity import AnimeIdentity
from core.models import PersonCredit
from sources.providers.anilist import AniListSource, BY_ID_QUERY, DETAIL_QUERY


class AniListLazyPeopleTests(unittest.IsolatedAsyncioTestCase):
    async def test_main_metadata_query_does_not_request_people(self) -> None:
        self.assertNotIn("staff(page:", DETAIL_QUERY)
        self.assertNotIn("characters(page:", DETAIL_QUERY)

        payload = {
            "Media": {
                "id": 101280,
                "idMal": 37430,
                "title": {
                    "romaji": "Tensei Shitara Slime Datta Ken",
                    "english": "That Time I Got Reincarnated as a Slime",
                    "native": "転生したらスライムだった件",
                },
                "synonyms": [],
                "format": "TV",
                "status": "FINISHED",
                "description": "Test",
                "startDate": {"year": 2018, "month": 10, "day": 2},
                "endDate": {"year": 2019, "month": 3, "day": 19},
                "season": "FALL",
                "seasonYear": 2018,
                "episodes": 24,
                "duration": 23,
                "averageScore": 80,
                "genres": ["Fantasy"],
                "isAdult": False,
                "coverImage": {"extraLarge": "https://example.invalid/poster.jpg"},
                "siteUrl": "https://anilist.co/anime/101280",
                "nextAiringEpisode": None,
                "studios": {"nodes": [{"name": "8bit"}]},
            }
        }

        with patch(
            "sources.providers.anilist.graphql_request", new=AsyncMock(return_value=payload)
        ) as graphql:
            record = await AniListSource().get_details(AnimeIdentity({"mal": "37430"}))

        self.assertIsNotNone(record)
        assert record is not None
        self.assertEqual(record.staff, [])
        self.assertEqual(record.voices, [])
        self.assertEqual(record.external_ids["anilist"], "101280")
        graphql.assert_awaited_once()

    async def test_people_cache_is_owned_by_source_instance(self) -> None:
        identity = AnimeIdentity({"anilist": "101280"})
        people = [PersonCredit(name="Test Staff")]
        first = AniListSource()
        second = AniListSource()

        with patch(
            "sources.providers.anilist._all_staff",
            new=AsyncMock(return_value=people),
        ) as load_staff:
            first_result = await first.load_staff(identity)
            cached_result = await first.load_staff(identity)
            second_result = await second.load_staff(identity)

        self.assertEqual(first_result[0].name, "Test Staff")
        self.assertEqual(cached_result[0].name, "Test Staff")
        self.assertEqual(second_result[0].name, "Test Staff")
        self.assertEqual(load_staff.await_count, 2)

    async def test_direct_anilist_identity_uses_anilist_id_query(self) -> None:
        payload = {
            "Media": {
                "id": 101280,
                "idMal": 37430,
                "title": {"romaji": "Slime", "english": None, "native": None},
                "synonyms": [],
                "format": "TV",
                "status": "FINISHED",
                "description": "",
                "startDate": {},
                "endDate": {},
                "season": None,
                "seasonYear": None,
                "episodes": 24,
                "duration": 23,
                "averageScore": 80,
                "genres": [],
                "isAdult": False,
                "coverImage": {},
                "siteUrl": "https://anilist.co/anime/101280",
                "nextAiringEpisode": None,
                "studios": {"nodes": []},
            }
        }
        with patch(
            "sources.providers.anilist.graphql_request", new=AsyncMock(return_value=payload)
        ) as graphql:
            record = await AniListSource().get_details(
                AnimeIdentity({"anilist": "101280"})
            )

        self.assertIsNotNone(record)
        assert record is not None
        self.assertEqual(record.source_id, "101280")
        self.assertEqual(record.external_ids["mal"], "37430")
        graphql.assert_awaited_once_with(
            BY_ID_QUERY,
            {"id": 101280},
            unittest.mock.ANY,
        )


if __name__ == "__main__":
    unittest.main()
