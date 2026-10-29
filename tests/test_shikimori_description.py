from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, patch

from core.identity import AnimeIdentity
from sources.providers.shikimori import ShikimoriSource, _clean_description, _record


class ShikimoriDescriptionTests(unittest.IsolatedAsyncioTestCase):
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

    def test_initial_record_defers_screenshots_and_description(self) -> None:
        record = _record(
            {
                "id": "48316",
                "name": "Kage no Jitsuryokusha ni Naritakute!",
                "description": "Deferred",
                "poster": {},
                "screenshots": [{"originalUrl": "/system/screenshots/original/1.jpg"}],
            }
        )
        self.assertEqual(record.screenshots, [])
        self.assertEqual(record.descriptions, {})

    async def test_screenshots_are_loaded_only_by_lazy_capability(self) -> None:
        source = ShikimoriSource()
        payload = {
            "animes": [
                {
                    "id": "48316",
                    "screenshots": [
                        {"originalUrl": "/system/screenshots/original/1.jpg"},
                        {"x332Url": "https://cdn.example.invalid/2.jpg"},
                    ],
                }
            ]
        }
        with patch(
            "sources.providers.shikimori._graphql",
            new=AsyncMock(return_value=payload),
        ) as graphql:
            values = await source.load_screenshots(
                AnimeIdentity({"shikimori": "48316"})
            )
        self.assertEqual(
            values,
            [
                "https://shikimori.io/system/screenshots/original/1.jpg",
                "https://cdn.example.invalid/2.jpg",
            ],
        )
        self.assertEqual(graphql.await_args.kwargs["operation"], "screenshots")

    async def test_description_is_cleaned_by_lazy_capability(self) -> None:
        source = ShikimoriSource()
        payload = {
            "animes": [
                {
                    "id": "48316",
                    "description": (
                        "Кем вы хотели стать? "
                        "[character=171572]Сид[/character] знает свой ответ."
                    ),
                }
            ]
        }
        with patch(
            "sources.providers.shikimori._graphql",
            new=AsyncMock(return_value=payload),
        ) as graphql:
            details = await source.load_description(
                AnimeIdentity({"shikimori": "48316"})
            )
        self.assertEqual(
            details.description,
            "Кем вы хотели стать? Сид знает свой ответ.",
        )
        self.assertEqual(graphql.await_args.kwargs["operation"], "description")


if __name__ == "__main__":
    unittest.main()
