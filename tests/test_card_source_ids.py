from __future__ import annotations

import unittest

from bots.telegram.card.views.renderer import anime_sections, main_rich
from bots.telegram.card.features.mapping_ids import mapping_ids_pages
from bots.telegram.card.ui.keyboards import fallback_main_keyboard, navigation_keyboard
from localization import available_locales, text
from core.models import AggregatedAnime
from core.source_names import MAL_SOURCE_NAME


class CardSourceIdTests(unittest.TestCase):
    def test_main_card_shows_only_ids_for_contributing_metadata_sources(self) -> None:
        anime = AggregatedAnime(
            title="Example",
            amdb_id="amdb:18472",
            sources=[MAL_SOURCE_NAME, "AniList"],
            external_ids={
                "mal": "100",
                "anilist": "200",
                "shikimori": "300",
                "anidb": "400",
            },
        )

        main = anime_sections(anime, locale="en")["main"]

        self.assertIn("AMDB: 18472", main)
        self.assertIn("MAL: 100", main)
        self.assertIn("ANILIST: 200", main)
        self.assertNotIn("SHIKIMORI: 300", main)
        self.assertNotIn("ANIDB: 400", main)

    def test_show_all_button_appears_only_with_a_verified_amdb_id(self) -> None:
        anime = AggregatedAnime(
            title="Example",
            amdb_id="amdb:18472",
            sources=["AniList"],
            external_ids={"anilist": "200"},
        )
        source = anime_sections(anime, locale="ru")["main"]
        rich = main_rich("token", anime, source, locale="ru").html or ""
        self.assertIn("av:token:all_ids:0", rich)
        self.assertIn("Показать все", rich)
        self.assertIn("<caption><b>ID источников</b></caption>", rich)
        source_caption = rich.index("<caption><b>Источники</b></caption>")
        links_button = rich.index('data="av:token:links:0"')
        ids_caption = rich.index("<caption><b>ID источников</b></caption>")
        ids_position = rich.index("AMDB: 18472")
        table_end = rich.index("</table>", ids_position)
        all_ids_button = rich.index('data="av:token:all_ids:0"')
        self.assertLess(source_caption, links_button)
        self.assertLess(links_button, ids_caption)
        self.assertLess(ids_caption, ids_position)
        self.assertLess(ids_position, table_end)
        self.assertLess(table_end, all_ids_button)
        self.assertEqual(rich.count('data="av:token:all_ids:0"'), 1)
        self.assertIn(
            '<tg-button type="callback_data" data="av:token:all_ids:0">',
            rich[table_end:],
        )
        self.assertNotIn('style="link"', rich[table_end:])
        fallback = fallback_main_keyboard("token", locale="ru", show_all_ids=True)
        callbacks = [
            button.callback_data for row in fallback.inline_keyboard for button in row
        ]
        self.assertIn("av:token:all_ids:0", callbacks)

        unlinked = AggregatedAnime(title="Example")
        rich_without_anchor = (
            main_rich(
                "token",
                unlinked,
                anime_sections(unlinked, locale="ru")["main"],
                locale="ru",
            ).html
            or ""
        )
        self.assertNotIn("av:token:all_ids:0", rich_without_anchor)

    def test_full_id_pages_preserve_all_ids_and_back_navigation(self) -> None:
        source_ids = {
            "mal": ("100",),
            "anilist": ("200",),
            "anidb": ("300",),
            "tmdb_movie": ("987654",),
        }
        for locale in available_locales():
            with self.subTest(locale=locale):
                pages = mapping_ids_pages("amdb:18472", source_ids, locale=locale)
                self.assertEqual(len(pages), 1)
                self.assertIn("AMDB: 18472", pages[0])
                for provider, values in source_ids.items():
                    self.assertIn(f"{provider.upper()}: {values[0]}", pages[0])
                self.assertIn(text("card", "all_ids_title", locale=locale), pages[0])
                keyboard = navigation_keyboard(
                    "token",
                    AggregatedAnime(title="Test"),
                    "all_ids",
                    0,
                    1,
                    locale=locale,
                )
                self.assertEqual(
                    keyboard.inline_keyboard[-1][0].callback_data,
                    "av:token:main:0",
                )

        long_ids = {f"provider_{i:04d}": (str(i) * 12,) for i in range(140)}
        pages = mapping_ids_pages("amdb:18472", long_ids, locale="en")
        self.assertGreater(len(pages), 1)
        self.assertTrue(all(len(page) <= 3700 for page in pages))
        for provider, values in long_ids.items():
            self.assertEqual(
                sum(f"{provider.upper()}: {values[0]}" in page for page in pages), 1
            )

    def test_mapping_only_ids_remain_available_to_internal_identity(self) -> None:
        anime = AggregatedAnime(
            title="Example",
            sources=["Shikimori"],
            external_ids={
                "shikimori": "10",
                "mal": "20",
                "anilist": "30",
                "anidb": "40",
            },
        )

        self.assertEqual(
            anime.identity.external_ids,
            {
                "shikimori": "10",
                "mal": "20",
                "anilist": "30",
                "anidb": "40",
            },
        )
        main = anime_sections(anime, locale="ru")["main"]
        self.assertIn("SHIKIMORI: 10", main)
        self.assertNotIn("MAL: 20", main)
        self.assertNotIn("ANILIST: 30", main)
        self.assertNotIn("ANIDB: 40", main)
        self.assertNotIn("AMDB:", main)


if __name__ == "__main__":
    unittest.main()
