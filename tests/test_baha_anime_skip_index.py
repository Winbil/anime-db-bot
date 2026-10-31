from __future__ import annotations

import importlib.util
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "update-baha-anime-skip.py"
SPEC = importlib.util.spec_from_file_location("update_baha_anime_skip", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class BahaAnimeSkipIndexTests(unittest.TestCase):
    def test_episode_video_map_prefers_primary_group_and_rejects_ambiguity(self) -> None:
        anime = {
            "episodes": {
                "0": [
                    {"episode": 1, "videoSn": 100},
                    {"episode": 2, "videoSn": 200},
                    {"episode": 2, "videoSn": 201},
                ],
                "special": [{"episode": 1, "videoSn": 999}],
            }
        }
        self.assertEqual(MODULE._episode_video_map(anime), {1: "100"})

    def test_database_contains_only_timestamped_episodes(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            output = root / "baha.sqlite3"
            mappings = root / "mappings.db"
            indexed = MODULE._create_database(
                output,
                timestamp_data={
                    "100": {"OP": [1.0, 90.0], "ED": [1200.0, 80.0]},
                    "300": {"OP": [2.0, 88.0]},
                },
                anime_payloads=[
                    (
                        "42",
                        {
                            "episodes": {
                                "0": [
                                    {"episode": 1, "videoSn": 100},
                                    {"episode": 2, "videoSn": 200},
                                ]
                            }
                        },
                        None,
                    )
                ],
                data_url="https://example.test/data.json",
                data_sha256="abc",
                mappings_path=mappings,
            )
            self.assertEqual(indexed, (1, 1, 2))
            with sqlite3.connect(output) as conn:
                rows = conn.execute(
                    "SELECT anime_sn, episode_number, video_sn, kind, start_seconds, end_seconds "
                    "FROM segments ORDER BY kind"
                ).fetchall()
                metadata = dict(conn.execute("SELECT key, value FROM metadata"))
        self.assertEqual(
            rows,
            [
                ("42", 1, "100", "ending", 1200.0, 1280.0),
                ("42", 1, "100", "opening", 1.0, 91.0),
            ],
        )
        self.assertEqual(metadata["schema_version"], "1")
        self.assertEqual(metadata["segments"], "2")

    def test_bahamut_ids_are_collected_from_edges_and_manual_accepts(self) -> None:
        with TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "mappings.db"
            with sqlite3.connect(db_path) as conn:
                conn.executescript(
                    """
                    CREATE TABLE edges (
                        a_provider TEXT, a_id TEXT, b_provider TEXT, b_id TEXT,
                        status TEXT
                    );
                    CREATE TABLE mapping_overrides (
                        source_provider TEXT, source_id TEXT,
                        target_provider TEXT, target_id TEXT, action TEXT
                    );
                    """
                )
                conn.executemany(
                    "INSERT INTO edges VALUES (?, ?, ?, ?, ?)",
                    [
                        ("bahamut", "10", "mal", "1", "accepted"),
                        ("anilist", "2", "bahamut", "20", "accepted"),
                        ("bahamut", "30", "mal", "3", "rejected"),
                    ],
                )
                conn.execute(
                    "INSERT INTO mapping_overrides VALUES (?, ?, ?, ?, ?)",
                    ("mal", "4", "bahamut", "40", "accept"),
                )
            self.assertEqual(MODULE._bahamut_ids(db_path), ["10", "20", "40"])


if __name__ == "__main__":
    unittest.main()
