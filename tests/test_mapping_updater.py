from __future__ import annotations

import sqlite3
import tempfile
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from mappings.config import MappingSourceSpec
from mappings.database import MappingDatabaseBuilder, MappingRecord
from mappings.updater import _source_due, update_mapping_database


class MappingUpdaterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.path = self.root / "mappings.db"

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
        with MappingDatabaseBuilder(self.path) as builder:
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
            patch("mappings.updater.mappings_update_max_age_hours", return_value=1.0),
            patch("mappings.updater._download", side_effect=fake_download),
        ):
            self.assertIsNone(update_mapping_database(force=False))

        self.assertEqual(self.path.stat().st_ino, inode_before)
        with sqlite3.connect(self.path) as conn:
            checked = conn.execute(
                "SELECT downloaded_at FROM datasets WHERE name=?", (spec.name,)
            ).fetchone()[0]
        self.assertNotEqual(checked, old)

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
