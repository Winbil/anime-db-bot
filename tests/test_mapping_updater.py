from __future__ import annotations

import sqlite3
import tempfile
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from core.sqlite import managed_sqlite_connection
from mappings.config import MappingSourceSpec
from mappings.database import MappingDatabaseBuilder, MappingRecord
from mappings.updater import _source_due, update_mapping_database


class MappingUpdaterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.path = self.root / "mappings.db"
        self.evidence_path = self.root / "mappings-evidence.db"

    def tearDown(self) -> None:
        self.temp.cleanup()

    @staticmethod
    def _spec(*, interval: str = "default") -> MappingSourceSpec:
        return MappingSourceSpec(
            name="test-source",
            url="https://example.invalid/data.json",
            importer="test",
            required=True,
            license_note="test",
            check_interval=interval,
        )

    def _build_existing(self, spec: MappingSourceSpec, checked_at: str) -> None:
        with MappingDatabaseBuilder(self.path, evidence_path=self.evidence_path) as builder:
            builder.ingest_dataset(
                spec,
                [MappingRecord("1", {"mal": ("1",), "anidb": ("2",)}, "test", 90)],
                sha256="same-sha",
                downloaded_at=checked_at,
            )
            builder.finalize(built_at=checked_at)

    def test_unchanged_source_is_checked_without_replacing_database(self) -> None:
        old = "2020-01-01T00:00:00+00:00"
        spec = self._spec()
        self._build_existing(spec, old)
        inode_before = self.path.stat().st_ino

        def fake_download(_spec: MappingSourceSpec, target: Path) -> str:
            target.write_text("same", encoding="utf-8")
            return "same-sha"

        with (
            patch("mappings.updater.SOURCE_SPECS", (spec,)),
            patch("mappings.updater.mappings_db_path", return_value=self.path),
            patch(
                "mappings.updater.mappings_evidence_db_path",
                return_value=self.evidence_path,
            ),
            patch("mappings.updater.mappings_update_max_age_hours", return_value=1.0),
            patch("mappings.updater._download", side_effect=fake_download),
        ):
            self.assertIsNone(update_mapping_database(force=False))

        self.assertEqual(self.path.stat().st_ino, inode_before)
        with managed_sqlite_connection(sqlite3.connect(self.evidence_path)) as conn:
            checked = conn.execute(
                "SELECT downloaded_at FROM datasets WHERE name=?", (spec.name,)
            ).fetchone()[0]
        self.assertNotEqual(checked, old)

    def test_force_rebuild_separates_runtime_from_evidence_storage(self) -> None:
        spec = self._spec()

        def fake_download(_spec: MappingSourceSpec, target: Path) -> str:
            target.write_text("fixture", encoding="utf-8")
            return "fixture-sha"

        def fake_importer(_path: Path):
            yield MappingRecord(
                "1",
                {"mal": ("1",), "anidb": ("2",), "imdb": ("tt3",)},
                "test",
                95,
            )

        with (
            patch("mappings.updater.SOURCE_SPECS", (spec,)),
            patch("mappings.updater.mappings_db_path", return_value=self.path),
            patch(
                "mappings.updater.mappings_evidence_db_path",
                return_value=self.evidence_path,
            ),
            patch("mappings.updater.mappings_keep_previous", return_value=False),
            patch("mappings.updater.mappings_keep_downloads", return_value=False),
            patch("mappings.updater._download", side_effect=fake_download),
            patch.dict("mappings.updater.IMPORTERS", {"test": fake_importer}),
        ):
            stats = update_mapping_database(force=True)

        self.assertIsNotNone(stats)
        assert stats is not None
        self.assertEqual(stats.edges, 3)
        self.assertEqual(stats.accepted_edges, 3)
        self.assertTrue(self.path.is_file())
        self.assertTrue(self.evidence_path.is_file())

        with managed_sqlite_connection(sqlite3.connect(self.path)) as conn:
            runtime_tables = {
                str(row[0])
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
            self.assertIn("nodes", runtime_tables)
            self.assertIn("edges", runtime_tables)
            self.assertNotIn("datasets", runtime_tables)
            self.assertNotIn("edge_evidence", runtime_tables)
            role = conn.execute(
                "SELECT value FROM metadata WHERE key='database_role'"
            ).fetchone()[0]
            self.assertEqual(role, "runtime")

        with managed_sqlite_connection(sqlite3.connect(self.evidence_path)) as conn:
            evidence_tables = {
                str(row[0])
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
            self.assertIn("datasets", evidence_tables)
            self.assertIn("records", evidence_tables)
            self.assertIn("edge_evidence", evidence_tables)
            self.assertNotIn("edges", evidence_tables)
            role = conn.execute(
                "SELECT value FROM metadata WHERE key='database_role'"
            ).fetchone()[0]
            self.assertEqual(role, "evidence")

    def test_wikidata_uses_its_own_hour_interval(self) -> None:
        checked = datetime.fromtimestamp(
            time.time() - 2 * 3600, timezone.utc
        ).isoformat()
        state = {"test-source": ("sha", checked)}
        with (
            patch("mappings.updater.mappings_update_max_age_hours", return_value=1.0),
            patch(
                "mappings.updater.mappings_wikidata_check_interval_hours",
                return_value=168.0,
            ),
        ):
            self.assertTrue(_source_due(self._spec(), state))
            self.assertFalse(_source_due(self._spec(interval="wikidata"), state))


if __name__ == "__main__":
    unittest.main()
