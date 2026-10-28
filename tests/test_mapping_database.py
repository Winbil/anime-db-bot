from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from core.identity import AnimeIdentity
from mappings.config import MappingSourceSpec
from mappings.database import MappingDatabaseBuilder, MappingRecord
from mappings.importers import (
    import_anibridge,
    import_anime_lists,
    import_animap,
    import_fribb,
    import_kometa,
    import_manami,
)
from mappings.resolver import (
    MappingResolver,
    copy_mapping_overrides,
    delete_mapping_override,
    list_mapping_override_history,
    list_mapping_overrides,
    set_mapping_override,
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

    def _build(self, datasets: list[tuple[str, list[MappingRecord]]]) -> MappingResolver:
        with MappingDatabaseBuilder(self.path) as builder:
            for index, (name, records) in enumerate(datasets):
                builder.ingest_dataset(
                    self._spec(name),
                    records,
                    sha256=f"sha-{index}",
                    downloaded_at="2026-10-27T00:00:00+00:00",
                )
            builder.finalize(built_at="2026-10-27T00:00:00+00:00")
        return MappingResolver(self.path)

    def test_direct_high_trust_mapping_is_resolved_from_sqlite(self) -> None:
        resolver = self._build([("manami", [MappingRecord(
            record_key="1",
            ids={"mal": ("100",), "anidb": ("200",)},
            evidence_group="manami",
            weight=82,
        )])])
        self.assertEqual(
            resolver.resolve(AnimeIdentity({"mal": "100"})),
            {"anidb": "200"},
        )

    def test_correlated_derived_datasets_do_not_double_vote(self) -> None:
        edge = lambda key: MappingRecord(
            record_key=key,
            ids={"mal": ("100",), "anidb": ("200",)},
            evidence_group="manami",
            weight=60,
        )
        resolver = self._build([("fribb", [edge("a")]), ("kometa", [edge("b")])])
        self.assertEqual(resolver.resolve(AnimeIdentity({"mal": "100"})), {})
        with sqlite3.connect(self.path) as conn:
            row = conn.execute(
                "SELECT status, evidence_count, evidence_group_count FROM edges"
            ).fetchone()
        self.assertEqual(row, ("candidate", 2, 1))

    def test_independent_groups_can_corroborate_lower_weight_edge(self) -> None:
        resolver = self._build([
            ("a", [MappingRecord("1", {"mal": ("100",), "anidb": ("200",)}, "g1", 60)]),
            ("b", [MappingRecord("2", {"mal": ("100",), "anidb": ("200",)}, "g2", 60)]),
        ])
        self.assertEqual(
            resolver.resolve(AnimeIdentity({"mal": "100"})),
            {"anidb": "200"},
        )

    def test_one_to_many_conflict_is_directional(self) -> None:
        resolver = self._build([("animap", [
            MappingRecord("1", {"anidb": ("200",), "mal": ("100",)}, "animap", 95),
            MappingRecord("2", {"anidb": ("200",), "mal": ("101",)}, "animap", 95),
        ])])
        self.assertEqual(resolver.resolve(AnimeIdentity({"anidb": "200"})), {})
        self.assertEqual(
            resolver.resolve(AnimeIdentity({"mal": "100"})),
            {"anidb": "200"},
        )

    def test_mapping_enrichment_never_follows_arbitrary_transitive_chain(self) -> None:
        resolver = self._build([("direct", [
            MappingRecord("1", {"mal": ("100",), "anidb": ("200",)}, "direct", 90),
            MappingRecord("2", {"anidb": ("200",), "kitsu": ("300",)}, "direct", 90),
        ])])
        self.assertEqual(
            resolver.resolve(AnimeIdentity({"mal": "100"})),
            {"anidb": "200"},
        )
        self.assertEqual(
            resolver.resolve(AnimeIdentity({"anidb": "200"})),
            {"mal": "100", "kitsu": "300"},
        )

    def test_multiple_confirmed_seeds_must_agree_on_new_provider(self) -> None:
        resolver = self._build([("direct", [
            MappingRecord("1", {"mal": ("100",), "anidb": ("200",)}, "direct", 90),
            MappingRecord("2", {"anilist": ("150",), "anidb": ("200",)}, "direct", 90),
        ])])
        self.assertEqual(
            resolver.resolve(AnimeIdentity({"mal": "100", "anilist": "150"})),
            {"anidb": "200"},
        )

    def test_confirmed_source_id_is_never_overwritten(self) -> None:
        resolver = self._build([("direct", [
            MappingRecord("1", {"mal": ("100",), "anilist": ("300",)}, "direct", 90),
        ])])
        self.assertEqual(
            resolver.resolve(AnimeIdentity({"mal": "100", "anilist": "999"})),
            {},
        )

    def test_accept_override_replaces_automatic_route(self) -> None:
        resolver = self._build([("direct", [
            MappingRecord("1", {"mal": ("100",), "anidb": ("201",)}, "direct", 95),
        ])])
        set_mapping_override(
            "MAL",
            "100",
            "AniDB",
            "200",
            action="accept",
            reason="verified season split manually",
            path=self.path,
        )
        self.assertEqual(
            resolver.resolve(AnimeIdentity({"mal": "100"})),
            {"anidb": "200"},
        )
        override = list_mapping_overrides(self.path)[0]
        self.assertEqual(override.action, "accept")
        self.assertEqual(override.reason, "verified season split manually")

    def test_reject_override_removes_one_automatic_edge(self) -> None:
        resolver = self._build([("direct", [
            MappingRecord("1", {"mal": ("100",), "anidb": ("200",)}, "direct", 95),
        ])])
        set_mapping_override(
            "mal",
            "100",
            "anidb",
            "200",
            action="reject",
            reason="known wrong mapping",
            path=self.path,
        )
        self.assertEqual(resolver.resolve(AnimeIdentity({"mal": "100"})), {})
        self.assertTrue(delete_mapping_override("mal", "100", "anidb", "200", path=self.path))
        self.assertEqual(
            resolver.resolve(AnimeIdentity({"mal": "100"})),
            {"anidb": "200"},
        )

    def test_override_cannot_silently_replace_confirmed_target_id(self) -> None:
        resolver = self._build([("direct", [
            MappingRecord("1", {"mal": ("100",), "anilist": ("300",)}, "direct", 95),
        ])])
        set_mapping_override(
            "mal",
            "100",
            "anilist",
            "999",
            action="accept",
            reason="deliberate conflicting fixture",
            path=self.path,
        )
        self.assertEqual(
            resolver.resolve(AnimeIdentity({"mal": "100", "anilist": "300"})),
            {},
        )

    def test_override_audit_metadata_and_history_are_persisted(self) -> None:
        self._build([("direct", [
            MappingRecord("1", {"mal": ("100",), "anidb": ("200",)}, "direct", 95),
        ])])
        override = set_mapping_override(
            "mal", "100", "anidb", "201",
            action="accept", reason="verified", author="tester", path=self.path,
        )
        self.assertEqual(override.author, "tester")
        self.assertTrue(override.updated_at)
        self.assertTrue(delete_mapping_override(
            "mal", "100", "anidb", "201",
            reason="superseded", author="tester2", path=self.path,
        ))
        history = list_mapping_override_history(self.path)
        self.assertEqual([item.event for item in history], ["set", "delete"])
        self.assertEqual([item.author for item in history], ["tester", "tester2"])
        self.assertEqual(history[-1].reason, "superseded")

    def test_legacy_override_table_is_migrated_on_write(self) -> None:
        self._build([])
        with sqlite3.connect(self.path) as conn:
            conn.execute("DROP TABLE mapping_override_history")
            conn.execute("ALTER TABLE mapping_overrides RENAME TO mapping_overrides_new")
            conn.execute("""
                CREATE TABLE mapping_overrides (
                    source_provider TEXT NOT NULL,
                    source_id TEXT NOT NULL,
                    target_provider TEXT NOT NULL,
                    target_id TEXT NOT NULL,
                    action TEXT NOT NULL,
                    reason TEXT NOT NULL DEFAULT '',
                    PRIMARY KEY(source_provider, source_id, target_provider, target_id)
                ) WITHOUT ROWID
            """)
            conn.execute("""
                INSERT INTO mapping_overrides(
                    source_provider, source_id, target_provider, target_id, action, reason
                ) VALUES ('mal','1','anidb','2','accept','legacy')
            """)
            conn.execute("DROP TABLE mapping_overrides_new")
            conn.commit()
        self.assertEqual(list_mapping_overrides(self.path)[0].author, "")
        set_mapping_override(
            "mal", "1", "anidb", "2",
            action="reject", reason="updated", author="migration-test", path=self.path,
        )
        current = list_mapping_overrides(self.path)[0]
        self.assertEqual(current.author, "migration-test")
        self.assertEqual(current.action, "reject")
        self.assertEqual(len(list_mapping_override_history(self.path)), 1)

    def test_overrides_can_be_copied_into_atomic_rebuild(self) -> None:
        self._build([("direct", [
            MappingRecord("1", {"mal": ("100",), "anidb": ("200",)}, "direct", 95),
        ])])
        set_mapping_override(
            "mal",
            "100",
            "anidb",
            "201",
            action="accept",
            reason="preserve across rebuild",
            author="rebuild-test",
            path=self.path,
        )

        rebuilt_path = self.root / "mappings.db.new"
        with MappingDatabaseBuilder(rebuilt_path) as builder:
            builder.ingest_dataset(
                self._spec("direct"),
                [MappingRecord("1", {"mal": ("100",), "anidb": ("200",)}, "direct", 95)],
                sha256="sha-new",
                downloaded_at="2026-10-28T00:00:00+00:00",
            )
            self.assertEqual(copy_mapping_overrides(self.path, builder.conn), 1)
            builder.finalize(built_at="2026-10-28T00:00:00+00:00")

        rebuilt = MappingResolver(rebuilt_path)
        self.assertEqual(
            rebuilt.resolve(AnimeIdentity({"mal": "100"})),
            {"anidb": "201"},
        )
        self.assertEqual(len(list_mapping_overrides(rebuilt_path)), 1)
        self.assertEqual(list_mapping_overrides(rebuilt_path)[0].author, "rebuild-test")
        self.assertEqual(len(list_mapping_override_history(rebuilt_path)), 1)


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
