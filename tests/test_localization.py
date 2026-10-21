from __future__ import annotations

import unittest

import sources.anilist as anilist_source
import sources.mal as mal_source
import sources.shikimori as shikimori_source
from core.canonicalization import (
    canonical_genre,
    canonical_genre_key,
    canonical_role,
    canonical_role_key,
    display_person_name,
    is_primary_voice_role,
    localize_role_token,
    voice_role_token,
)
from localization import (
    available_locales,
    canonicalize_domain_value,
    locale_name,
    localize_source_value,
    source_canonical_key,
    source_value_key,
    text,
)


class LocalizationCatalogTests(unittest.TestCase):
    def test_locales_are_data_driven(self) -> None:
        self.assertEqual(set(available_locales()), {"ru", "en"})
        self.assertEqual(locale_name("ru", display_locale="ru"), "Русский")
        self.assertEqual(locale_name("en", display_locale="en"), "English")
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

    def test_dynamic_voice_roles_are_localized_only_at_render_time(self) -> None:
        token = voice_role_token("Rimuru Tempest")
        self.assertEqual(token, "voice_of::Rimuru Tempest")
        self.assertEqual(localize_role_token(token, locale="ru"), "Озвучка: Rimuru Tempest")
        self.assertEqual(localize_role_token(token, locale="en"), "Voice: Rimuru Tempest")

    def test_source_enum_mapping_is_separate_from_translation(self) -> None:
        self.assertEqual(
            source_canonical_key("mal", "status", "currently_airing"),
            ("anime_status", "airing"),
        )
        self.assertEqual(
            source_value_key("mal", "status", "currently_airing"),
            "airing",
        )
        self.assertEqual(
            localize_source_value("mal", "status", "currently_airing", locale="ru"),
            "выходит",
        )
        self.assertEqual(
            localize_source_value("mal", "status", "currently_airing", locale="en"),
            "Airing",
        )

    def test_localized_domain_values_can_be_normalized_back_to_keys(self) -> None:
        self.assertEqual(canonicalize_domain_value("anime_status", "выходит"), "airing")
        self.assertEqual(canonicalize_domain_value("anime_status", "Airing"), "airing")
        self.assertEqual(canonicalize_domain_value("season", "Весна"), "spring")
        self.assertEqual(canonicalize_domain_value("season", "Spring"), "spring")

    def test_people_display_is_computed_per_locale_without_nesting(self) -> None:
        name = "Jun Fukuyama"
        aliases = ["Дзюн Фукуяма", "福山 潤"]
        ru = display_person_name(name, aliases, locale="ru")
        en = display_person_name(name, aliases, locale="en")
        self.assertEqual(ru, "Дзюн Фукуяма (Jun Fukuyama, 福山 潤)")
        self.assertEqual(en, "Jun Fukuyama (福山 潤)")
        self.assertNotIn("Дзюн Фукуяма (Jun Fukuyama, Дзюн", ru)

    def test_source_adapters_no_longer_own_display_enum_maps(self) -> None:
        self.assertFalse(hasattr(anilist_source, "FORMAT_NAMES"))
        self.assertFalse(hasattr(anilist_source, "STATUS_NAMES"))
        self.assertFalse(hasattr(anilist_source, "SEASON_NAMES"))
        self.assertFalse(hasattr(mal_source, "MEDIA_TYPE_NAMES"))
        self.assertFalse(hasattr(mal_source, "SOURCE_NAMES"))
        self.assertFalse(hasattr(mal_source, "DAY_NAMES"))
        self.assertFalse(hasattr(shikimori_source, "KIND_NAMES"))
        self.assertFalse(hasattr(shikimori_source, "RATING_NAMES"))

    def test_unknown_source_values_are_preserved(self) -> None:
        self.assertEqual(
            source_value_key("mal", "status", "future_status"),
            "future_status",
        )
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
