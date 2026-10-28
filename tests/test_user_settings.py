from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from services.user_settings import SQLiteUserSettingsStore


class UserSettingsStoreTests(unittest.TestCase):
    def test_default_locale_is_russian(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = SQLiteUserSettingsStore(Path(directory) / "settings.sqlite3")
            self.assertEqual(store.get(123).locale, "ru")

    def test_locale_survives_new_repository_instance(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.sqlite3"
            first = SQLiteUserSettingsStore(path)
            self.assertEqual(first.set_locale(123, "en").locale, "en")

            second = SQLiteUserSettingsStore(path)
            self.assertEqual(second.get(123).locale, "en")
            self.assertEqual(second.get(999).locale, "ru")

    def test_unsupported_locale_falls_back_to_russian(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = SQLiteUserSettingsStore(Path(directory) / "settings.sqlite3")
            self.assertEqual(store.set_locale(123, "de").locale, "ru")

    def test_settings_are_platform_scoped(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = SQLiteUserSettingsStore(Path(directory) / "settings.sqlite3")
            store.set_locale(123, "en", platform="telegram")
            store.set_locale(123, "ru", platform="discord")

            self.assertEqual(store.get(123, platform="telegram").locale, "en")
            self.assertEqual(store.get(123, platform="discord").locale, "ru")

    def test_known_users_are_platform_scoped_and_persistent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.sqlite3"
            first = SQLiteUserSettingsStore(path)
            first.touch_user("telegram", 300)
            first.touch_user("telegram", 100)
            first.touch_user("discord", 200)

            second = SQLiteUserSettingsStore(path)
            self.assertEqual(second.list_user_ids("telegram"), [100, 300])
            self.assertEqual(second.list_user_ids("discord"), [200])

    def test_existing_settings_rows_are_backfilled_into_known_telegram_users(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.sqlite3"
            first = SQLiteUserSettingsStore(path)
            first.set_locale(777, "en")

            second = SQLiteUserSettingsStore(path)
            self.assertEqual(second.list_user_ids("telegram"), [777])

    def test_legacy_user_settings_schema_is_migrated_to_telegram(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.sqlite3"
            with sqlite3.connect(path) as connection:
                connection.execute(
                    """
                    CREATE TABLE user_settings (
                        user_id INTEGER PRIMARY KEY,
                        locale TEXT NOT NULL DEFAULT 'ru',
                        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
                connection.execute(
                    """
                    INSERT INTO user_settings(user_id, locale, updated_at)
                    VALUES (777, 'en', '2026-10-28 19:00:00')
                    """
                )

            store = SQLiteUserSettingsStore(path)
            self.assertEqual(store.get(777, platform="telegram").locale, "en")
            self.assertEqual(store.get(777, platform="discord").locale, "ru")
            self.assertEqual(store.list_user_ids("telegram"), [777])

            with sqlite3.connect(path) as connection:
                columns = {
                    str(row[1])
                    for row in connection.execute("PRAGMA table_info(user_settings)")
                }
                rows = connection.execute(
                    "SELECT platform, user_id, locale FROM user_settings"
                ).fetchall()
            self.assertIn("platform", columns)
            self.assertEqual(rows, [("telegram", 777, "en")])


if __name__ == "__main__":
    unittest.main()
