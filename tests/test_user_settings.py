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


if __name__ == "__main__":
    unittest.main()
