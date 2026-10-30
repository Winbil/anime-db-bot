from __future__ import annotations

import unittest

from bots.telegram.callbacks import (
    EpisodeDetailCallback,
    KeyedPageCallback,
    PagePickerCallback,
    SectionSourceCallback,
    SettingsCallback,
    TokenCallback,
    TokenIndexCallback,
    TokenValueCallback,
    ViewCallback,
    resolve_key_or_legacy_index,
)


class CallbackCodecTests(unittest.TestCase):
    def test_view_round_trip_preserves_wire_format(self) -> None:
        value = ViewCallback("abc", "voices", 12)
        self.assertEqual(value.encode(), "av:abc:voices:12")
        self.assertEqual(ViewCallback.parse(value.encode()), value)

    def test_section_source_codec_uses_stable_key_and_accepts_legacy_index(
        self,
    ) -> None:
        value = SectionSourceCallback("abc", "staff", "anilist", 9)
        self.assertEqual(value.encode(), "as:abc:staff:anilist:9")
        self.assertEqual(SectionSourceCallback.parse(value.encode()), value)
        self.assertEqual(
            SectionSourceCallback.parse("as:abc:staff:2:9"),
            SectionSourceCallback("abc", "staff", "2", 9),
        )

    def test_legacy_index_resolver_maps_old_position_to_current_key(self) -> None:
        keys = ["shikimori", "anilist", "mal"]
        self.assertEqual(resolve_key_or_legacy_index("anilist", keys), "anilist")
        self.assertEqual(resolve_key_or_legacy_index("1", keys), "anilist")
        with self.assertRaises(ValueError):
            resolve_key_or_legacy_index("9", keys)

    def test_keyed_page_codec_supports_stable_and_legacy_selectors(self) -> None:
        stable = KeyedPageCallback("ap", "abc", "anidb", 4)
        self.assertEqual(stable.encode(), "ap:abc:anidb:4")
        self.assertEqual(KeyedPageCallback.parse(stable.encode(), prefix="ap"), stable)
        legacy = KeyedPageCallback.parse("ap:abc:1:4", prefix="ap")
        self.assertEqual(legacy, KeyedPageCallback("ap", "abc", "1", 4))

    def test_episode_detail_parser_accepts_legacy_and_stable_payloads(self) -> None:
        self.assertEqual(
            EpisodeDetailCallback.parse("ae:abc:7:2"),
            EpisodeDetailCallback("abc", "0", 7, 2),
        )
        self.assertEqual(
            EpisodeDetailCallback.parse("ae:abc:1:7:2"),
            EpisodeDetailCallback("abc", "1", 7, 2),
        )
        current = EpisodeDetailCallback("abc", "anidb", 7, 2)
        self.assertEqual(current.encode(), "ae:abc:anidb:7:2")
        self.assertEqual(EpisodeDetailCallback.parse(current.encode()), current)

    def test_search_callback_codecs_preserve_wire_format(self) -> None:
        scope = TokenValueCallback("sc", "abc", "anilist")
        self.assertEqual(scope.encode(), "sc:abc:anilist")
        self.assertEqual(TokenValueCallback.parse(scope.encode(), prefix="sc"), scope)
        cancel = TokenCallback("sx", "abc")
        self.assertEqual(cancel.encode(), "sx:abc")
        self.assertEqual(TokenCallback.parse(cancel.encode(), prefix="sx"), cancel)
        result = TokenIndexCallback("sr", "abc", 4)
        self.assertEqual(result.encode(), "sr:abc:4")
        self.assertEqual(TokenIndexCallback.parse(result.encode(), prefix="sr"), result)

    def test_page_picker_codec_preserves_route_and_window(self) -> None:
        value = PagePickerCallback("cp", "abc", "as~staff~anilist", 32, 75, 1)
        self.assertEqual(value.encode(), "cp:abc:as~staff~anilist:32:75:1")
        self.assertEqual(PagePickerCallback.parse(value.encode(), prefix="cp"), value)
        self.assertIsNone(
            PagePickerCallback.parse("cp:abc:as~staff~anilist:75:75:2", prefix="cp")
        )

    def test_settings_callback_codec_preserves_wire_format(self) -> None:
        language = SettingsCallback("language")
        self.assertEqual(language.encode(), "settings:language")
        self.assertEqual(SettingsCallback.parse(language.encode()), language)
        locale = SettingsCallback("locale", "ru")
        self.assertEqual(locale.encode(), "settings:locale:ru")
        self.assertEqual(SettingsCallback.parse(locale.encode()), locale)

    def test_invalid_or_oversized_callbacks_are_rejected(self) -> None:
        self.assertIsNone(ViewCallback.parse("av:abc:voices:nope"))
        with self.assertRaises(ValueError):
            ViewCallback("x" * 60, "voices", 0).encode()
        with self.assertRaises(ValueError):
            ViewCallback("bad:token", "voices", 0).encode()


if __name__ == "__main__":
    unittest.main()
