from __future__ import annotations

import unittest
from datetime import datetime, timezone

from bots.telegram.card.renderer import anime_sections
from core.models import AggregatedAnime, AnimeRecord, EpisodeRecord
from core.temporal import PartialDate, parse_datetime, parse_partial_date
from services.aggregation_merge import _consensus_datetime, _consensus_partial_date
from services.direct_lookup import _record_year
from sources.anilist import _format_date as anilist_date
from sources.anilist import _format_timestamp as anilist_timestamp
from sources.jikan import _episode as jikan_episode


class PartialDateTests(unittest.TestCase):
    def test_preserves_year_month_and_day_precision(self) -> None:
        self.assertEqual(parse_partial_date("2026"), PartialDate(2026))
        self.assertEqual(parse_partial_date("2026-04"), PartialDate(2026, 4))
        self.assertEqual(parse_partial_date("2026-04-01"), PartialDate(2026, 4, 1))
        self.assertEqual(PartialDate(2026).isoformat(), "2026")
        self.assertEqual(PartialDate(2026, 4).isoformat(), "2026-04")
        self.assertEqual(PartialDate(2026, 4, 1).isoformat(), "2026-04-01")

    def test_invalid_calendar_values_are_rejected(self) -> None:
        self.assertIsNone(parse_partial_date("2026-02-30"))
        self.assertIsNone(parse_partial_date("2026-13"))
        self.assertIsNone(parse_partial_date({"year": 2026, "day": 1}))
        self.assertEqual(parse_partial_date("2024-02-29"), PartialDate(2024, 2, 29))

    def test_datetime_input_keeps_only_date_for_episode_domain(self) -> None:
        self.assertEqual(
            parse_partial_date("2026-02-02T12:34:56+00:00"),
            PartialDate(2026, 2, 2),
        )


class TypedTemporalModelTests(unittest.TestCase):
    def test_models_normalize_legacy_string_inputs(self) -> None:
        anime = AnimeRecord(
            source="Test",
            source_id="1",
            aired_on="2026-04",
            released_on="2026-09-16",
            next_episode_at="2026-04-02T12:30:00Z",
        )
        episode = EpisodeRecord(
            number=1,
            source="mal",
            backend="jikan",
            aired_at="2026-04-01T00:00:00+00:00",
        )
        self.assertEqual(anime.aired_on, PartialDate(2026, 4))
        self.assertEqual(anime.released_on, PartialDate(2026, 9, 16))
        self.assertEqual(
            anime.next_episode_at,
            datetime(2026, 4, 2, 12, 30, tzinfo=timezone.utc),
        )
        self.assertEqual(episode.aired_at, PartialDate(2026, 4, 1))

    def test_renderer_keeps_existing_iso_visible_format(self) -> None:
        anime = AggregatedAnime(
            title="Temporal",
            aired_on="2026-04",
            released_on="2026-09-16",
            next_episode_at="2026-04-02T12:30:00+00:00",
        )
        rendered = anime_sections(anime, locale="ru")["main"]
        self.assertIn("2026-04", rendered)
        self.assertIn("2026-09-16", rendered)
        self.assertIn("2026-04-02T12:30:00+00:00", rendered)


class TemporalAggregationTests(unittest.TestCase):
    def test_date_and_datetime_consensus_return_typed_values(self) -> None:
        records = [
            AnimeRecord(
                source="A",
                source_id="1",
                aired_on="2026-04",
                next_episode_at="2026-04-02T12:30:00+00:00",
            ),
            AnimeRecord(
                source="B",
                source_id="2",
                aired_on="2026-04",
                next_episode_at="2026-04-02T12:30:00+00:00",
            ),
            AnimeRecord(
                source="C",
                source_id="3",
                aired_on="2026-04-01",
                next_episode_at="2026-04-02T13:30:00+00:00",
            ),
        ]
        self.assertEqual(_consensus_partial_date(records, "aired_on"), PartialDate(2026, 4))
        self.assertEqual(
            _consensus_datetime(records, "next_episode_at"),
            datetime(2026, 4, 2, 12, 30, tzinfo=timezone.utc),
        )

    def test_direct_lookup_uses_typed_year(self) -> None:
        record = AnimeRecord(source="A", source_id="1", aired_on="2026-04")
        self.assertEqual(_record_year(record), 2026)


class TemporalSourceAdapterTests(unittest.TestCase):
    def test_anilist_keeps_partial_date_and_aware_timestamp(self) -> None:
        self.assertEqual(
            anilist_date({"year": 2026, "month": 4, "day": None}),
            PartialDate(2026, 4),
        )
        self.assertEqual(
            anilist_timestamp(1775133000),
            datetime.fromtimestamp(1775133000, tz=timezone.utc),
        )

    def test_jikan_episode_discards_time_not_date(self) -> None:
        episode = jikan_episode({
            "number": 1,
            "aired_at": "2026-01-01T08:30:00+00:00",
        })
        self.assertEqual(episode.aired_at, PartialDate(2026, 1, 1))

    def test_invalid_iso_timestamp_is_none(self) -> None:
        self.assertIsNone(parse_datetime("not-a-timestamp"))
