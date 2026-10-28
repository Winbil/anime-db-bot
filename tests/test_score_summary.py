from __future__ import annotations

import math
import unittest

from core.score_summary import consensus_score, normalize_source_scores


class ScoreSummaryTests(unittest.TestCase):
    def test_equal_source_mean_keeps_sources_neutral(self) -> None:
        self.assertEqual(consensus_score([8.0, 9.0, 7.0]), 8.0)

    def test_invalid_scores_are_removed_from_map_and_count(self) -> None:
        scores = normalize_source_scores({
            "MAL": 8.0,
            "AniList": "9",
            "broken": math.nan,
            "too-high": 11,
            "empty": None,
        })
        self.assertEqual(scores, {"MAL": 8.0, "AniList": 9.0})
        self.assertEqual(consensus_score(scores.values()), 8.5)

    def test_no_valid_scores_returns_none(self) -> None:
        self.assertIsNone(consensus_score([None, "bad", math.inf, -1, 99]))
