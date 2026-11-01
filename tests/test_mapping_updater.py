from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import zstandard as zstd

from core.identity import AnimeIdentity
from mappings.resolver import MappingResolver, set_mapping_override
from mappings.updater import update_mapping_database
from tests.mapping_fixtures import create_runtime_mapping_db


class MappingReleaseUpdaterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.active = self.root / "active" / "mappings.db"
        self.manifest_path = self.root / "active" / "manifest.json"
        self.canonical = self.root / "release" / "mappings.db"
        self.compressed = self.root / "release" / "mappings.db.zst"
        self.repository = "anime-db-project/anime-mapping-db"
        self.fingerprint = "a" * 64

    def tearDown(self) -> None:
        self.temp.cleanup()

    @staticmethod
    def _sha256(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def _prepare_release(self) -> dict[str, object]:
        create_runtime_mapping_db(
            self.canonical,
            [("mal", "100", "anidb", "200")],
        )
        compressor = zstd.ZstdCompressor(level=3)
        self.compressed.parent.mkdir(parents=True, exist_ok=True)
        with self.canonical.open("rb") as source, self.compressed.open("wb") as target:
            compressor.copy_stream(source, target)
        return {
            "repository": self.repository,
            "release_tag": "v2026.11.01-test",
            "schema_version": 3,
            "source_fingerprint": self.fingerprint,
            "counts": {
                "datasets": 1,
                "records": 1,
                "edges": 1,
                "accepted_edges": 1,
                "conflicts": 0,
            },
            "assets": {
                "runtime": {
                    "name": "mappings.db",
                    "size": self.canonical.stat().st_size,
                    "sha256": self._sha256(self.canonical),
                },
                "runtime_zstd": {
                    "name": "mappings.db.zst",
                    "size": self.compressed.stat().st_size,
                    "sha256": self._sha256(self.compressed),
                },
            },
        }

    def _patch_settings(self):
        return (
            patch("mappings.updater.mappings_db_path", return_value=self.active),
            patch(
                "mappings.updater.mappings_manifest_path",
                return_value=self.manifest_path,
            ),
            patch(
                "mappings.updater.mappings_release_repository",
                return_value=self.repository,
            ),
            patch("mappings.updater.mappings_keep_previous", return_value=False),
        )

    def test_download_validates_and_preserves_local_admin_overrides(self) -> None:
        manifest = self._prepare_release()
        create_runtime_mapping_db(
            self.active,
            [("mal", "100", "anidb", "200")],
        )
        set_mapping_override(
            "mal",
            "100",
            "anidb",
            "201",
            action="accept",
            reason="local production correction",
            path=self.active,
        )

        def fake_download(_url: str, target: Path) -> str:
            shutil.copy2(self.compressed, target)
            return self._sha256(target)

        patches = self._patch_settings()
        with (
            patches[0],
            patches[1],
            patches[2],
            patches[3],
            patch("mappings.updater._fetch_manifest", return_value=manifest),
            patch("mappings.updater._download", side_effect=fake_download),
        ):
            result = update_mapping_database(force=False)

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.release_tag, "v2026.11.01-test")
        self.assertEqual(result.overrides_preserved, 1)
        self.assertEqual(
            MappingResolver(self.active).resolve(AnimeIdentity({"mal": "100"})),
            {"anidb": "201"},
        )
        installed = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(installed["source_fingerprint"], self.fingerprint)

    def test_same_release_identity_skips_database_download(self) -> None:
        manifest = self._prepare_release()
        create_runtime_mapping_db(
            self.active,
            [("mal", "100", "anidb", "200")],
        )
        self.manifest_path.parent.mkdir(parents=True, exist_ok=True)
        self.manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        patches = self._patch_settings()
        with (
            patches[0],
            patches[1],
            patches[2],
            patches[3],
            patch("mappings.updater._fetch_manifest", return_value=manifest),
            patch("mappings.updater._download") as download,
        ):
            self.assertIsNone(update_mapping_database(force=False))
        download.assert_not_called()

    def test_new_release_with_same_source_fingerprint_is_downloaded(self) -> None:
        manifest = self._prepare_release()
        create_runtime_mapping_db(
            self.active,
            [("mal", "100", "anidb", "200")],
        )
        installed = dict(manifest)
        installed["release_tag"] = "v2026.11.01-older-engine"
        self.manifest_path.parent.mkdir(parents=True, exist_ok=True)
        self.manifest_path.write_text(json.dumps(installed), encoding="utf-8")

        def fake_download(_url: str, target: Path) -> str:
            shutil.copy2(self.compressed, target)
            return self._sha256(target)

        patches = self._patch_settings()
        with (
            patches[0],
            patches[1],
            patches[2],
            patches[3],
            patch("mappings.updater._fetch_manifest", return_value=manifest),
            patch("mappings.updater._download", side_effect=fake_download) as download,
        ):
            result = update_mapping_database(force=False)

        self.assertIsNotNone(result)
        download.assert_called_once()
        updated = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(updated["release_tag"], manifest["release_tag"])
        self.assertEqual(updated["source_fingerprint"], self.fingerprint)

    def test_failed_hash_never_replaces_active_database(self) -> None:
        manifest = self._prepare_release()
        create_runtime_mapping_db(
            self.active,
            [("mal", "100", "anidb", "999")],
        )
        before = self._sha256(self.active)

        def fake_download(_url: str, target: Path) -> str:
            shutil.copy2(self.compressed, target)
            return "0" * 64

        patches = self._patch_settings()
        with (
            patches[0],
            patches[1],
            patches[2],
            patches[3],
            patch("mappings.updater._fetch_manifest", return_value=manifest),
            patch("mappings.updater._download", side_effect=fake_download),
        ):
            with self.assertRaises(RuntimeError):
                update_mapping_database(force=True)
        self.assertEqual(self._sha256(self.active), before)
        self.assertFalse(self.manifest_path.exists())


if __name__ == "__main__":
    unittest.main()
