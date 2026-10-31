from __future__ import annotations

import json
import re
import unittest
from importlib import resources

import sources.providers.anilist as anilist_source
import sources.providers.mal as mal_source
import sources.providers.shikimori as shikimori_source
from bots.telegram.card.features.descriptions import _preferred_description
from bots.telegram.settings import _language_keyboard
from core.canonicalization import (
    canonical_genre,
    canonical_genre_key,
    canonical_role,
    canonical_role_key,
    canonical_role_token,
    display_person_name,
    is_primary_voice_role,
    localize_role_token,
    voice_role_token,
)
from core.models import DescriptionDetails
from localization import (
    DEFAULT_LOCALE,
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
        self.assertEqual(DEFAULT_LOCALE, "en")
        self.assertEqual(
            set(available_locales()), {"ru", "en", "ja", "de", "es", "fr", "it"}
        )
        expected_names = {
            "ru": "Русский",
            "en": "English",
            "ja": "日本語",
            "de": "Deutsch",
            "es": "Español",
            "fr": "Français",
            "it": "Italiano",
        }
        for locale, name in expected_names.items():
            self.assertEqual(locale_name(locale, display_locale=locale), name)
        self.assertEqual(text("genres", "fantasy", locale="ru"), "Фэнтези")
        self.assertEqual(text("genres", "fantasy", locale="en"), "Fantasy")
        self.assertEqual(text("genres", "fantasy", locale="ja"), "ファンタジー")

    def test_every_locale_catalog_is_complete_and_preserves_placeholders(self) -> None:
        locale_dir = resources.files("localization").joinpath("locales")
        catalogs = {
            locale: json.loads(
                locale_dir.joinpath(f"{locale}.json").read_text(encoding="utf-8")
            )
            for locale in available_locales()
        }

        def flatten(
            value: object, prefix: tuple[str, ...] = ()
        ) -> dict[tuple[str, ...], str]:
            if isinstance(value, dict):
                result: dict[tuple[str, ...], str] = {}
                for key, child in value.items():
                    result.update(flatten(child, (*prefix, str(key))))
                return result
            return {prefix: str(value)}

        english = flatten(catalogs["en"])
        english_keys = set(english)
        placeholder_re = re.compile(r"\{[^{}]+\}")
        for locale, catalog in catalogs.items():
            with self.subTest(locale=locale):
                flattened = flatten(catalog)
                self.assertEqual(set(flattened), english_keys)
                for key, source in english.items():
                    self.assertEqual(
                        sorted(placeholder_re.findall(flattened[key])),
                        sorted(placeholder_re.findall(source)),
                        f"placeholder mismatch for {locale}:{'.'.join(key)}",
                    )

    def test_new_western_locales_do_not_fall_back_to_english_ui(self) -> None:
        native_names = {
            "de": "Deutsch",
            "es": "Español",
            "fr": "Français",
            "it": "Italiano",
        }
        for locale, native_name in native_names.items():
            with self.subTest(locale=locale):
                self.assertEqual(
                    locale_name(locale, display_locale=locale), native_name
                )
                self.assertNotEqual(
                    text("settings", "title", locale=locale),
                    text("settings", "title", locale="en"),
                )
                self.assertNotEqual(
                    text("common", "unknown", locale=locale),
                    text("common", "unknown", locale="en"),
                )

    def test_genre_aliases_resolve_to_canonical_keys(self) -> None:
        self.assertEqual(canonical_genre_key("Action"), "action")
        self.assertEqual(canonical_genre_key("боевик"), "action")
        self.assertEqual(canonical_genre("Action"), "Action")
        self.assertEqual(canonical_genre("Action", locale="en"), "Action")
        self.assertEqual(canonical_genre("Action", locale="ja"), "アクション")

    def test_kitsu_category_aliases_are_localized(self) -> None:
        expected = {
            "Fantasy World": ("fantasy_world", "Фэнтезийный мир", "ファンタジー世界"),
            "Parody": ("parody", "Пародия", "パロディ"),
            "Swordplay": ("swordplay", "Бои на мечах", "剣術"),
            "School Life": ("school_life", "Школьная жизнь", "学園生活"),
            "Elf": ("elf", "Эльфы", "エルフ"),
            "Harem": ("harem", "Гарем", "ハーレム"),
            "Juujin": ("beastfolk", "Зверолюди", "獣人"),
            "Vampires": ("vampire", "Вампиры", "吸血鬼"),
        }
        for raw, (key, ru, ja) in expected.items():
            with self.subTest(raw=raw):
                self.assertEqual(canonical_genre_key(raw), key)
                self.assertEqual(canonical_genre(raw, locale="ru"), ru)
                self.assertEqual(canonical_genre(raw, locale="ja"), ja)

    def test_role_aliases_resolve_to_canonical_keys(self) -> None:
        self.assertEqual(canonical_role_key("Director"), "director")
        self.assertEqual(canonical_role("Director"), "Director")
        self.assertEqual(canonical_role("Director", locale="en"), "Director")
        self.assertEqual(canonical_role("Director", locale="ja"), "監督")
        self.assertEqual(canonical_role("Director (Series)"), "Director (Series)")
        self.assertTrue(is_primary_voice_role("Сэйю"))
        self.assertFalse(is_primary_voice_role("Сэйю (EN)"))

    def test_language_picker_exposes_every_supported_locale(self) -> None:
        keyboard = _language_keyboard("de")
        language_buttons = [row[0] for row in keyboard.inline_keyboard[:-1]]
        self.assertEqual(
            [button.callback_data for button in language_buttons],
            [
                "settings:locale:en",
                "settings:locale:ru",
                "settings:locale:ja",
                "settings:locale:de",
                "settings:locale:es",
                "settings:locale:fr",
                "settings:locale:it",
            ],
        )
        self.assertEqual(
            [button.text.lstrip("✓ ") for button in language_buttons],
            [
                "🇬🇧 English",
                "🇷🇺 Русский",
                "🇯🇵 日本語",
                "🇩🇪 Deutsch",
                "🇪🇸 Español",
                "🇫🇷 Français",
                "🇮🇹 Italiano",
            ],
        )
        self.assertTrue(language_buttons[3].text.startswith("✓ "))

    def test_source_provided_descriptions_follow_interface_locale_with_english_fallback(
        self,
    ) -> None:
        details = DescriptionDetails(
            description="English fallback",
            localized_descriptions={
                "en": "English synopsis",
                "de": "Deutsche Beschreibung",
                "es": "Descripción española",
            },
        )
        self.assertEqual(_preferred_description(details, "de"), "Deutsche Beschreibung")
        self.assertEqual(_preferred_description(details, "es"), "Descripción española")
        self.assertEqual(_preferred_description(details, "fr"), "English synopsis")

    def test_dynamic_voice_roles_are_localized_only_at_render_time(self) -> None:
        token = voice_role_token("Rimuru Tempest")
        self.assertEqual(token, "voice_of::Rimuru Tempest")
        self.assertEqual(
            localize_role_token(token, locale="ru"), "Озвучка: Rimuru Tempest"
        )
        self.assertEqual(
            localize_role_token(token, locale="en"), "Voice: Rimuru Tempest"
        )
        self.assertEqual(localize_role_token(token, locale="ja"), "声: Rimuru Tempest")
        self.assertEqual(
            localize_role_token(token, locale="de"), "Stimme: Rimuru Tempest"
        )
        self.assertEqual(localize_role_token(token, locale="es"), "Voz: Rimuru Tempest")
        self.assertEqual(
            localize_role_token(token, locale="fr"), "Voix : Rimuru Tempest"
        )
        self.assertEqual(
            localize_role_token(token, locale="it"), "Voce: Rimuru Tempest"
        )
        for rendered in (
            "Stimme: Rimuru Tempest",
            "Voz: Rimuru Tempest",
            "Voix : Rimuru Tempest",
            "Voce: Rimuru Tempest",
        ):
            self.assertEqual(canonical_role_token(rendered), token)

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
        self.assertEqual(
            localize_source_value("mal", "status", "currently_airing", locale="ja"),
            "放送中",
        )

    def test_localized_domain_values_can_be_normalized_back_to_keys(self) -> None:
        self.assertEqual(canonicalize_domain_value("anime_status", "выходит"), "airing")
        self.assertEqual(canonicalize_domain_value("anime_status", "Airing"), "airing")
        self.assertEqual(canonicalize_domain_value("anime_status", "放送中"), "airing")
        self.assertEqual(canonicalize_domain_value("season", "Весна"), "spring")
        self.assertEqual(canonicalize_domain_value("season", "Spring"), "spring")
        self.assertEqual(canonicalize_domain_value("season", "春"), "spring")

    def test_people_display_is_computed_per_locale_without_nesting(self) -> None:
        name = "Jun Fukuyama"
        aliases = ["Дзюн Фукуяма", "福山 潤"]
        ru = display_person_name(name, aliases, locale="ru")
        en = display_person_name(name, aliases, locale="en")
        ja = display_person_name(name, aliases, locale="ja")
        self.assertEqual(ru, "Дзюн Фукуяма (Jun Fukuyama, 福山 潤)")
        self.assertEqual(en, "Jun Fukuyama (福山 潤)")
        self.assertEqual(ja, "福山 潤 (Jun Fukuyama)")
        for locale in ("de", "es", "fr", "it"):
            self.assertEqual(
                display_person_name(name, aliases, locale=locale),
                "Jun Fukuyama (福山 潤)",
            )
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

    def test_platform_ui_sections_are_available_in_all_locales(self) -> None:
        self.assertEqual(text("search_ui", "details", locale="en"), "Details")
        self.assertEqual(text("search_ui", "details", locale="ru"), "Подробнее")
        self.assertEqual(text("search_ui", "details", locale="ja"), "詳細")
        self.assertEqual(text("admin", "forbidden", locale="ja"), "権限がありません。")
        self.assertIn(
            "5 秒後",
            text("rate_limit", "too_many_requests", locale="ja", seconds=5),
        )
        for locale in ("de", "es", "fr", "it"):
            self.assertTrue(text("search_ui", "details", locale=locale).strip())
            self.assertTrue(text("admin", "forbidden", locale=locale).strip())

    def test_template_text_supports_parameters(self) -> None:
        self.assertEqual(
            text("common", "voice_of", locale="ru", name="Римуру"),
            "Озвучка: Римуру",
        )
        self.assertEqual(
            text("common", "voice_of", locale="en", name="Rimuru"),
            "Voice: Rimuru",
        )
        self.assertEqual(
            text("common", "voice_of", locale="ja", name="リムル"),
            "声: リムル",
        )


if __name__ == "__main__":
    unittest.main()
