from __future__ import annotations

import unittest

from sources.anilist import _record as anilist_record
from sources.mal import _record as mal_record
from sources.shikimori import _record as shikimori_record


class PopularitySourceParsingTests(unittest.TestCase):
    def test_mal_keeps_public_list_statistics(self) -> None:
        record = mal_record(
            {
                "id": 1,
                "title": "Example",
                "mean": 8.1,
                "rank": 123,
                "popularity": 45,
                "num_list_users": 1000,
                "num_scoring_users": 700,
                "num_favorites": 80,
                "statistics": {
                    "num_list_users": 1000,
                    "status": {
                        "watching": "100",
                        "completed": "600",
                        "on_hold": "50",
                        "dropped": "20",
                        "plan_to_watch": "230",
                    },
                },
            }
        )

        self.assertEqual(record.rank, 123)
        self.assertEqual(record.popularity_rank, 45)
        self.assertEqual(record.list_users, 1000)
        self.assertEqual(record.scoring_users, 700)
        self.assertEqual(record.favorites, 80)
        self.assertEqual(
            record.status_distribution,
            {
                "watching": 100,
                "completed": 600,
                "on_hold": 50,
                "dropped": 20,
                "planned": 230,
            },
        )
        self.assertEqual(record.score_distribution, {})

    def test_anilist_normalizes_audience_histograms_and_rankings(self) -> None:
        record = anilist_record(
            {
                "id": 10,
                "idMal": 20,
                "title": {"romaji": "Example"},
                "averageScore": 82,
                "popularity": 1500,
                "favourites": 90,
                "rankings": [
                    {"rank": 100, "type": "RATED", "allTime": True},
                    {"rank": 50, "type": "POPULAR", "allTime": True},
                    {"rank": 7, "type": "RATED", "year": 2026, "season": "SPRING", "allTime": False},
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
        )

        self.assertEqual(record.rank, 100)
        self.assertEqual(record.popularity_rank, 50)
        self.assertEqual(record.list_users, 1500)
        self.assertEqual(record.scoring_users, 900)
        self.assertEqual(record.favorites, 90)
        self.assertEqual(
            record.status_distribution,
            {"watching": 100, "completed": 900, "planned": 500},
        )
        self.assertEqual(record.score_distribution, {8: 400, 9: 300, 10: 200})
        self.assertEqual(record.rankings[2].season, "spring")
        self.assertEqual(record.rankings[2].year, 2026)

    def test_shikimori_derives_totals_from_public_distributions(self) -> None:
        record = shikimori_record(
            {
                "id": "30",
                "malId": "20",
                "name": "Example",
                "score": 8.2,
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
        )

        self.assertEqual(record.list_users, 950)
        self.assertEqual(record.scoring_users, 750)
        self.assertEqual(record.status_distribution["planned"], 300)
        self.assertEqual(record.score_distribution, {10: 200, 9: 300, 8: 250})


if __name__ == "__main__":
    unittest.main()
