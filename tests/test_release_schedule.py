from __future__ import annotations

import unittest
from datetime import datetime, time, timezone

from bots.telegram.card.views.renderer import anime_sections
from core.models import AggregatedAnime, AnimeRecord, BroadcastSlot
from services.aggregation.merge import _consensus_rating
from services.aggregation.release_schedule import build_episode_release_schedule
from sources.providers.anilist import _record as anilist_record
from sources.providers.shikimori import _record as shikimori_record


class ReleaseScheduleTests(unittest.TestCase):
    def test_source_next_date_projects_all_remaining_tv_episodes(self) -> None:
        first = datetime(2026, 11, 1, 18, 0, tzinfo=timezone.utc)
        schedule = build_episode_release_schedule(
            status="airing",
            kind="tv",
            episodes_total=12,
            episodes_aired=7,
            next_episode_at=first,
            next_episode_number=8,
            broadcasts=[],
            now=datetime(2026, 10, 31, 12, 0, tzinfo=timezone.utc),
        )

        self.assertEqual([item.episode_number for item in schedule], [8, 9, 10, 11, 12])
        self.assertFalse(schedule[0].estimated)
        self.assertTrue(all(item.estimated for item in schedule[1:]))
        self.assertEqual(schedule[-1].airs_at, first.replace(day=29))

    def test_broadcast_slot_can_estimate_nearest_episode_when_sources_have_no_date(
        self,
    ) -> None:
        schedule = build_episode_release_schedule(
            status="airing",
            kind="tv",
            episodes_total=3,
            episodes_aired=1,
            next_episode_at=None,
            next_episode_number=None,
            broadcasts=[BroadcastSlot(weekday="monday", time=time(20, 0))],
            now=datetime(2026, 11, 1, 10, 0, tzinfo=timezone.utc),
        )

        self.assertEqual([item.episode_number for item in schedule], [2, 3])
        self.assertTrue(all(item.estimated for item in schedule))
        self.assertEqual(
            schedule[0].airs_at.isoformat(),
            "2026-11-02T20:00:00+09:00",
        )
        self.assertEqual(
            schedule[1].airs_at.isoformat(),
            "2026-11-09T20:00:00+09:00",
        )

    def test_finished_title_never_gets_projected_future_dates(self) -> None:
        schedule = build_episode_release_schedule(
            status="finished",
            kind="tv",
            episodes_total=12,
            episodes_aired=12,
            next_episode_at=datetime(2026, 11, 1, tzinfo=timezone.utc),
            next_episode_number=13,
            broadcasts=[BroadcastSlot(weekday="monday", time=time(20, 0))],
            now=datetime(2026, 10, 31, tzinfo=timezone.utc),
        )
        self.assertEqual(schedule, [])

    def test_unknown_total_keeps_only_known_next_release(self) -> None:
        schedule = build_episode_release_schedule(
            status="airing",
            kind="tv",
            episodes_total=None,
            episodes_aired=7,
            next_episode_at=datetime(2026, 11, 1, 18, 0, tzinfo=timezone.utc),
            next_episode_number=8,
            broadcasts=[],
            now=datetime(2026, 10, 31, 12, 0, tzinfo=timezone.utc),
        )
        self.assertEqual(len(schedule), 1)
        self.assertFalse(schedule[0].estimated)

    def test_card_shows_explicit_episode_counts_and_projection_provenance(self) -> None:
        schedule = build_episode_release_schedule(
            status="airing",
            kind="tv",
            episodes_total=10,
            episodes_aired=7,
            next_episode_at=datetime(2026, 11, 1, 18, 0, tzinfo=timezone.utc),
            next_episode_number=8,
            broadcasts=[],
            now=datetime(2026, 10, 31, 12, 0, tzinfo=timezone.utc),
        )
        anime = AggregatedAnime(
            title="Example",
            kind="tv",
            status="airing",
            rating="pg_13",
            episodes_total=10,
            episodes_aired=7,
            next_episode_at=schedule[0].airs_at,
            next_episode_number=8,
            episode_release_schedule=schedule,
        )

        ru = anime_sections(anime, locale="ru")
        self.assertIn("Вышло серий: 7", ru["main"])
        self.assertIn("Всего серий: 10", ru["main"])
        self.assertIn("Возрастной рейтинг: PG-13", ru["main"])
        self.assertIn("Следующая серия №8", ru["main"])
        self.assertIn("Серия 8:", ru["release_schedule"])
        self.assertIn("дата источника", ru["release_schedule"])
        self.assertIn("Серия 9:", ru["release_schedule"])
        self.assertIn("предположительно", ru["release_schedule"])
        self.assertIn("недельному интервалу", ru["release_schedule"])


class ReleaseMetadataNormalizationTests(unittest.TestCase):
    def test_age_rating_ignores_unrated_and_uses_more_restrictive_tie(self) -> None:
        records = [
            AnimeRecord(source="A", source_id="1", rating="none"),
            AnimeRecord(source="B", source_id="2", rating="pg_13"),
        ]
        self.assertEqual(_consensus_rating(records), "pg_13")

        tie = [
            AnimeRecord(source="A", source_id="1", rating="pg"),
            AnimeRecord(source="B", source_id="2", rating="r"),
        ]
        self.assertEqual(_consensus_rating(tie), "r")

    def test_anilist_preserves_next_episode_number(self) -> None:
        record = anilist_record(
            {
                "id": 1,
                "status": "RELEASING",
                "episodes": 12,
                "nextAiringEpisode": {"episode": 8, "airingAt": 1793565600},
            }
        )
        self.assertEqual(record.status, "airing")
        self.assertEqual(record.episodes_total, 12)
        self.assertEqual(record.episodes_aired, 7)
        self.assertEqual(record.next_episode_number, 8)
        self.assertIsNotNone(record.next_episode_at)

    def test_shikimori_derives_next_episode_number_from_aired_count(self) -> None:
        record = shikimori_record(
            {
                "id": "1",
                "status": "ongoing",
                "episodes": 12,
                "episodesAired": 7,
                "nextEpisodeAt": "2026-11-01T18:00:00+00:00",
            }
        )
        self.assertEqual(record.status, "airing")
        self.assertEqual(record.episodes_total, 12)
        self.assertEqual(record.episodes_aired, 7)
        self.assertEqual(record.next_episode_number, 8)
        self.assertIsNotNone(record.next_episode_at)


if __name__ == "__main__":
    unittest.main()
