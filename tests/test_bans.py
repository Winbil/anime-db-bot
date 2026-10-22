from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from services.bans import SQLiteBanStore


class BanStoreTests(unittest.TestCase):
    def test_permanent_ban_survives_repository_restart(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bans.sqlite3"
            first = SQLiteBanStore(path)
            first.ban("telegram", 100, banned_by=1, reason="spam", now=1_000)

            second = SQLiteBanStore(path)
            ban = second.get_active("telegram", 100, now=2_000)
            self.assertIsNotNone(ban)
            assert ban is not None
            self.assertTrue(ban.permanent)
            self.assertEqual(ban.reason, "spam")
            self.assertEqual(ban.banned_by, 1)

    def test_temporary_ban_expires_and_is_removed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = SQLiteBanStore(Path(directory) / "bans.sqlite3")
            store.ban(
                "telegram",
                100,
                banned_by=1,
                duration_seconds=60,
                now=1_000,
            )
            self.assertIsNotNone(store.get_active("telegram", 100, now=1_059))
            self.assertIsNone(store.get_active("telegram", 100, now=1_060))
            self.assertIsNone(store.get_active("telegram", 100, now=1_061))

    def test_reban_replaces_existing_record(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = SQLiteBanStore(Path(directory) / "bans.sqlite3")
            store.ban("telegram", 100, banned_by=1, reason="first", now=1_000)
            store.ban(
                "telegram",
                100,
                banned_by=2,
                duration_seconds=30,
                reason="second",
                now=2_000,
            )
            ban = store.get_active("telegram", 100, now=2_010)
            self.assertIsNotNone(ban)
            assert ban is not None
            self.assertEqual(ban.reason, "second")
            self.assertEqual(ban.banned_by, 2)
            self.assertEqual(ban.expires_at, 2_030)

    def test_unban_removes_record(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = SQLiteBanStore(Path(directory) / "bans.sqlite3")
            store.ban("telegram", 100, banned_by=1)
            self.assertTrue(store.unban("telegram", 100))
            self.assertFalse(store.unban("telegram", 100))
            self.assertIsNone(store.get_active("telegram", 100))

    def test_invalid_duration_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = SQLiteBanStore(Path(directory) / "bans.sqlite3")
            with self.assertRaises(ValueError):
                store.ban("telegram", 100, banned_by=1, duration_seconds=0)


if __name__ == "__main__":
    unittest.main()
