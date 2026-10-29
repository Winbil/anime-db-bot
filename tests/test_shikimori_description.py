from __future__ import annotations

import unittest

from sources.providers.shikimori import _clean_description, _record


class ShikimoriDescriptionTests(unittest.TestCase):
    def test_character_markup_keeps_visible_name(self) -> None:
        source = (
            "Наш герой [character=171572]Сид[/character] появляется в нужный момент."
        )

        self.assertEqual(
            _clean_description(source),
            "Наш герой Сид появляется в нужный момент.",
        )

    def test_common_bbcode_and_html_are_removed_without_losing_text(self) -> None:
        source = (
            "[b]Начало[/b][br]"
            "[url=https://example.invalid]ссылка[/url] и "
            "[anime=48316]аниме[/anime].<br><i>Конец</i>"
        )

        self.assertEqual(
            _clean_description(source),
            "Начало\nссылка и аниме.\nКонец",
        )

    def test_record_stores_screenshot_urls(self) -> None:
        record = _record(
            {
                "id": "48316",
                "name": "Kage no Jitsuryokusha ni Naritakute!",
                "poster": {},
                "screenshots": [
                    {
                        "originalUrl": "/system/screenshots/original/1.jpg",
                        "x332Url": "/system/screenshots/x332/1.jpg",
                    },
                    {"x332Url": "https://cdn.example.invalid/2.jpg"},
                ],
            }
        )

        self.assertEqual(
            record.screenshots,
            [
                "https://shikimori.io/system/screenshots/original/1.jpg",
                "https://cdn.example.invalid/2.jpg",
            ],
        )

    def test_record_stores_clean_shikimori_description(self) -> None:
        record = _record(
            {
                "id": "48316",
                "malId": "48316",
                "name": "Kage no Jitsuryokusha ni Naritakute!",
                "description": (
                    "Кем вы хотели стать? "
                    "[character=171572]Сид[/character] знает свой ответ."
                ),
                "poster": {},
            }
        )

        self.assertEqual(
            record.descriptions["Shikimori"],
            "Кем вы хотели стать? Сид знает свой ответ.",
        )


if __name__ == "__main__":
    unittest.main()
