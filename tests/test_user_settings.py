from __future__ import annotations

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


if __name__ == "__main__":
    unittest.main()
