from __future__ import annotations

import unittest

from core.canonicalization import (
    canonical_genre,
    canonical_genre_key,
    canonical_role,
    canonical_role_key,
    is_primary_voice_role,
)
from localization import available_locales, localize_source_value, source_canonical_key, text


class LocalizationCatalogTests(unittest.TestCase):
    def test_locales_are_data_driven(self) -> None:
        self.assertIn("ru", available_locales())
        self.assertIn("en", available_locales())
        self.assertEqual(text("genres", "fantasy", locale="ru"), "Фэнтези")
        self.assertEqual(text("genres", "fantasy", locale="en"), "Fantasy")

    def test_genre_aliases_resolve_to_canonical_keys(self) -> None:
        self.assertEqual(canonical_genre_key("Action"), "action")
        self.assertEqual(canonical_genre_key("боевик"), "action")
        self.assertEqual(canonical_genre("Action"), "Экшен")
        self.assertEqual(canonical_genre("Action", locale="en"), "Action")

    def test_role_aliases_resolve_to_canonical_keys(self) -> None:
        self.assertEqual(canonical_role_key("Director"), "director")
        self.assertEqual(canonical_role("Director"), "Режиссёр")
        self.assertEqual(canonical_role("Director", locale="en"), "Director")
        self.assertEqual(canonical_role("Director (Series)"), "Режиссёр (Series)")
        self.assertTrue(is_primary_voice_role("Сэйю"))
        self.assertFalse(is_primary_voice_role("Сэйю (EN)"))

    def test_source_enum_mapping_is_separate_from_translation(self) -> None:
        self.assertEqual(
            source_canonical_key("mal", "status", "currently_airing"),
            ("anime_status", "airing"),
        )
        self.assertEqual(
            localize_source_value("mal", "status", "currently_airing", locale="ru"),
            "выходит",
        )
        self.assertEqual(
            localize_source_value("mal", "status", "currently_airing", locale="en"),
            "Airing",
        )

    def test_unknown_source_values_are_preserved(self) -> None:
        self.assertEqual(
            localize_source_value("mal", "status", "future_status"),
            "future_status",
        )

    def test_template_text_supports_parameters(self) -> None:
        self.assertEqual(
            text("common", "voice_of", locale="ru", name="Римуру"),
            "Озвучка: Римуру",
        )
        self.assertEqual(
            text("common", "voice_of", locale="en", name="Rimuru"),
            "Voice: Rimuru",
        )


if __name__ == "__main__":
    unittest.main()
