from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, patch

from core.identity import AnimeIdentity
from sources.providers.anilist import AniListSource, _record as anilist_record
from sources.providers.mal import MALSource, _record as mal_record
from sources.providers.shikimori import ShikimoriSource, _record as shikimori_record


class PopularitySourceParsingTests(unittest.IsolatedAsyncioTestCase):
    def test_initial_records_defer_detailed_popularity(self) -> None:
        mal = mal_record(
            {
                "id": 1,
                "title": "Example",
                "mean": 8.1,
                "rank": 123,
                "popularity": 45,
                "num_list_users": 1000,
                "statistics": {"status": {"completed": "600"}},
            }
        )
        anilist = anilist_record(
            {
                "id": 10,
                "title": {"romaji": "Example"},
                "averageScore": 82,
                "popularity": 1500,
                "rankings": [{"rank": 100, "type": "RATED", "allTime": True}],
            }
        )
        shikimori = shikimori_record(
            {
                "id": "30",
                "name": "Example",
                "score": 8.2,
                "statusesStats": [{"status": "completed", "count": 500}],
                "poster": {},
            }
        )

        self.assertEqual(mal.score, 8.1)
        self.assertIsNone(mal.rank)
        self.assertEqual(mal.status_distribution, {})
        self.assertEqual(anilist.score, 8.2)
        self.assertIsNone(anilist.rank)
        self.assertEqual(anilist.rankings, [])
        self.assertEqual(shikimori.score, 8.2)
        self.assertIsNone(shikimori.list_users)
        self.assertEqual(shikimori.status_distribution, {})

    async def test_mal_lazy_popularity_merges_official_and_jikan_statistics(
        self,
    ) -> None:
        source = MALSource()
        source._jikan.load_popularity_supplement = AsyncMock(
            return_value={10: 100, 9: 50}
        )
        payload = {
            "rank": 123,
            "popularity": 45,
            "num_list_users": 1000,
            "num_scoring_users": 700,
            "num_favorites": 80,
            "statistics": {
                "status": {
                    "watching": "100",
                    "completed": "600",
                    "on_hold": "50",
                    "dropped": "20",
                    "plan_to_watch": "230",
                }
            },
        }
        with patch(
            "sources.providers.mal._get_raw", new=AsyncMock(return_value=payload)
        ) as getter:
            stats = await source.load_popularity(AnimeIdentity({"mal": "1"}))

        self.assertEqual(stats.rank, 123)
        self.assertEqual(stats.popularity_rank, 45)
        self.assertEqual(stats.list_users, 1000)
        self.assertEqual(stats.scoring_users, 700)
        self.assertEqual(stats.favorites, 80)
        self.assertEqual(stats.status_distribution["planned"], 230)
        self.assertEqual(stats.score_distribution, {10: 100, 9: 50})
        self.assertEqual(getter.await_args.kwargs["operation"], "popularity")
        source._jikan.load_popularity_supplement.assert_awaited_once()

    async def test_anilist_lazy_popularity_normalizes_histograms_and_rankings(
        self,
    ) -> None:
        source = AniListSource()
        payload = {
            "Media": {
                "id": 10,
                "popularity": 1500,
                "favourites": 90,
                "rankings": [
                    {"rank": 100, "type": "RATED", "allTime": True},
                    {"rank": 50, "type": "POPULAR", "allTime": True},
                    {
                        "rank": 7,
                        "type": "RATED",
                        "year": 2026,
                        "season": "SPRING",
                        "allTime": False,
                    },
                ],
                "stats": {
                    "statusDistribution": [
                        {"status": "CURRENT", "amount": 100},
                        {"status": "COMPLETED", "amount": 900},
                        {"status": "PLANNING", "amount": 500},
                    ],
                    "scoreDistribution": [
                        {"score": 80, "amount": 400},
                        {"score": 90, "amount": 300},
                        {"score": 100, "amount": 200},
                    ],
                },
            }
        }
        with patch(
            "sources.providers.anilist.graphql_request",
            new=AsyncMock(return_value=payload),
        ) as graphql:
            stats = await source.load_popularity(AnimeIdentity({"anilist": "10"}))

        self.assertEqual(stats.rank, 100)
        self.assertEqual(stats.popularity_rank, 50)
        self.assertEqual(stats.list_users, 1500)
        self.assertEqual(stats.scoring_users, 900)
        self.assertEqual(stats.favorites, 90)
        self.assertEqual(
            stats.status_distribution,
            {"watching": 100, "completed": 900, "planned": 500},
        )
        self.assertEqual(stats.score_distribution, {8: 400, 9: 300, 10: 200})
        self.assertEqual(stats.rankings[2].season, "spring")
        self.assertEqual(graphql.await_args.kwargs["operation"], "popularity")

    async def test_shikimori_lazy_popularity_derives_totals(self) -> None:
        source = ShikimoriSource()
        payload = {
            "animes": [
                {
                    "id": "30",
                    "statusesStats": [
                        {"status": "planned", "count": 300},
                        {"status": "completed", "count": 500},
                        {"status": "watching", "count": 100},
                        {"status": "dropped", "count": 20},
                        {"status": "on_hold", "count": 30},
                    ],
                    "scoresStats": [
                        {"score": 10, "count": 200},
                        {"score": 9, "count": 300},
                        {"score": 8, "count": 250},
                    ],
                }
            ]
        }
        with patch(
            "sources.providers.shikimori._graphql",
            new=AsyncMock(return_value=payload),
        ) as graphql:
            stats = await source.load_popularity(AnimeIdentity({"shikimori": "30"}))

        self.assertEqual(stats.list_users, 950)
        self.assertEqual(stats.scoring_users, 750)
        self.assertEqual(stats.status_distribution["planned"], 300)
        self.assertEqual(stats.score_distribution, {10: 200, 9: 300, 8: 250})
        self.assertEqual(graphql.await_args.kwargs["operation"], "popularity")


if __name__ == "__main__":
    unittest.main()
