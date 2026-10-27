from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from core.identity import AnimeIdentity
from mappings.config import MappingSourceSpec
from mappings.database import MappingDatabase, MappingDatabaseBuilder, MappingRecord
from mappings.importers import (
    import_anibridge,
    import_anime_lists,
    import_animap,
    import_fribb,
    import_kometa,
    import_manami,
)


class MappingDatabaseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.path = self.root / "mappings.db"

    def tearDown(self) -> None:
        self.temp.cleanup()

    @staticmethod
    def _spec(name: str) -> MappingSourceSpec:
        return MappingSourceSpec(
            name=name,
            url="https://example.invalid/data",
            importer="test",
            required=True,
            license_note="test",
        )

    def _build(self, datasets: list[tuple[str, list[MappingRecord]]]) -> MappingDatabase:
        with MappingDatabaseBuilder(self.path) as builder:
            for index, (name, records) in enumerate(datasets):
                builder.ingest_dataset(
                    self._spec(name),
                    records,
                    sha256=f"sha-{index}",
                    downloaded_at="2026-10-27T00:00:00+00:00",
                )
            builder.finalize(built_at="2026-10-27T00:00:00+00:00")
        return MappingDatabase(self.path)

    def test_direct_high_trust_mapping_is_resolved_from_sqlite(self) -> None:
        db = self._build([("manami", [MappingRecord(
            record_key="1",
            ids={"mal": ("100",), "anidb": ("200",)},
            evidence_group="manami",
            weight=82,
        )])])
        self.assertEqual(db.resolve(AnimeIdentity({"mal": "100"})), {"anidb": "200"})

    def test_correlated_derived_datasets_do_not_double_vote(self) -> None:
        edge = lambda key: MappingRecord(
            record_key=key,
            ids={"mal": ("100",), "anidb": ("200",)},
            evidence_group="manami",
            weight=60,
        )
        db = self._build([("fribb", [edge("a")]), ("kometa", [edge("b")])])
        self.assertEqual(db.resolve(AnimeIdentity({"mal": "100"})), {})
        with db._connect() as conn:
            row = conn.execute(
                "SELECT status, evidence_count, evidence_group_count FROM edges"
            ).fetchone()
        self.assertEqual(row, ("candidate", 2, 1))

    def test_independent_groups_can_corroborate_lower_weight_edge(self) -> None:
        db = self._build([
            ("a", [MappingRecord("1", {"mal": ("100",), "anidb": ("200",)}, "g1", 60)]),
            ("b", [MappingRecord("2", {"mal": ("100",), "anidb": ("200",)}, "g2", 60)]),
        ])
        self.assertEqual(db.resolve(AnimeIdentity({"mal": "100"})), {"anidb": "200"})

    def test_one_to_many_conflict_is_directional(self) -> None:
        db = self._build([("animap", [
            MappingRecord("1", {"anidb": ("200",), "mal": ("100",)}, "animap", 95),
            MappingRecord("2", {"anidb": ("200",), "mal": ("101",)}, "animap", 95),
        ])])
        self.assertEqual(db.resolve(AnimeIdentity({"anidb": "200"})), {})
        self.assertEqual(db.resolve(AnimeIdentity({"mal": "100"})), {"anidb": "200"})

    def test_recursive_graph_expands_multiple_safe_ids(self) -> None:
        db = self._build([("direct", [
            MappingRecord("1", {"mal": ("100",), "anidb": ("200",)}, "direct", 90),
            MappingRecord("2", {"anidb": ("200",), "kitsu": ("300",)}, "direct", 90),
        ])])
        resolved = db.resolve(AnimeIdentity({"mal": "100"}))
        self.assertEqual(resolved["anidb"], "200")
        self.assertEqual(resolved["kitsu"], "300")

    def test_confirmed_source_id_is_never_overwritten(self) -> None:
        db = self._build([("direct", [
            MappingRecord("1", {"mal": ("100",), "anidb": ("200",)}, "direct", 90),
            MappingRecord("2", {"anidb": ("200",), "anilist": ("300",)}, "direct", 90),
        ])])
        self.assertEqual(
            db.resolve(AnimeIdentity({"mal": "100", "anilist": "999"})),
            {},
        )


class MappingImporterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_all_supported_importers_stream_small_fixtures(self) -> None:
        fribb = self.root / "fribb.json"
        fribb.write_text(json.dumps([{
            "anidb_id": 10,
            "mal_id": 20,
            "anilist_id": 30,
            "tvdb_id": 40,
            "themoviedb_id": {"tv": 50, "movie": [60]},
        }]), encoding="utf-8")
        self.assertTrue(any(record.ids.get("mal") == ("20",) for record in import_fribb(fribb)))

        kometa = self.root / "kometa.json"
        kometa.write_text(json.dumps({"10": {
            "mal_id": "20", "anilist_id": "30", "tvdb_id": "40", "tmdb_show_id": "50"
        }}), encoding="utf-8")
        self.assertTrue(any(record.ids.get("anidb") == ("10",) for record in import_kometa(kometa)))

        anime_lists = self.root / "anime-list.xml"
        anime_lists.write_text(
            '<anime-list><anime anidbid="10" tvdbid="40" tmdbtv="50" tmdbid="60" imdbid="tt70" /></anime-list>',
            encoding="utf-8",
        )
        self.assertEqual(next(import_anime_lists(anime_lists)).ids["tvdb"], ("40",))

        animap = self.root / "animap.json"
        animap.write_text(json.dumps({
            "entries": [{"anilist_id": 30, "ids": {"anidb": [10], "mal": [20]}}],
            "anime": [{"anidb_id": 10, "mal_ids": [20], "tvdb_id": 40, "imdb_ids": ["tt70"]}],
        }), encoding="utf-8")
        animap_records = list(import_animap(animap))
        self.assertTrue(any(record.ids.get("anilist") == ("30",) for record in animap_records))

        manami = self.root / "manami.jsonl"
        manami.write_text(
            json.dumps({"sources": [
                "https://anidb.net/anime/10",
                "https://anilist.co/anime/30",
                "https://myanimelist.net/anime/20",
            ]}) + "\n",
            encoding="utf-8",
        )
        self.assertEqual(next(import_manami(manami)).ids["mal"], ("20",))

        anibridge = self.root / "anibridge.json"
        anibridge.write_text(json.dumps({
            "anidb:10:R": {"mal:20": {"1-12": "1-12"}}
        }), encoding="utf-8")
        record = next(import_anibridge(anibridge))
        self.assertEqual(record.ids["anidb"], ("10",))
        self.assertEqual(record.ids["mal"], ("20",))


if __name__ == "__main__":
    unittest.main()
