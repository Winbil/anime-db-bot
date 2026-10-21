from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, patch

from sources.anilist import AniListSource, DETAIL_QUERY


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

        with patch("sources.anilist._graphql", new=AsyncMock(return_value=payload)) as graphql:
            record = await AniListSource().get_details("37430", {"mal": "37430"})

        self.assertIsNotNone(record)
        assert record is not None
        self.assertEqual(record.staff, [])
        self.assertEqual(record.voices, [])
        self.assertEqual(record.external_ids["anilist"], "101280")
        graphql.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
