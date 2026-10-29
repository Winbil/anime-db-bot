from __future__ import annotations

import unittest

from bots.telegram.card.ui.keyboards import (
    description_selection_rows,
    source_section_selection_rows,
)
from bots.telegram.people.views import _keyboard as people_keyboard
from core.models import AggregatedAnime, PersonCredit


class StableSourceCallbackTests(unittest.TestCase):
    def test_description_buttons_use_source_keys(self) -> None:
        anime = AggregatedAnime(
            title="Example",
            sources=["AniList", "MAL (MyAnimeList) / Jikan"],
            descriptions={
                "AniList": "A",
                "MAL (MyAnimeList) / Jikan": "B",
            },
        )
        rows = description_selection_rows("token", anime)
        callbacks = [button.callback_data for row in rows for button in row]
        self.assertEqual(callbacks, ["ad:token:anilist:0", "ad:token:mal:0"])

    def test_source_section_buttons_use_source_keys(self) -> None:
        anime = AggregatedAnime(
            title="Example",
            sources=["AniList", "Shikimori"],
            titles_by_source={
                "AniList": {"romaji": "Example"},
                "Shikimori": {"romaji": "Example"},
            },
        )
        rows = source_section_selection_rows("token", anime, "titles", locale="ru")
        callbacks = [button.callback_data for row in rows for button in row]
        self.assertIn("as:token:titles:anilist:0", callbacks)
        self.assertIn("as:token:titles:shikimori:0", callbacks)

    def test_people_buttons_use_source_keys(self) -> None:
        person = PersonCredit(
            name="Voice",
            portraits={"AniList": ["https://img.example/voice.jpg"]},
        )
        anime = AggregatedAnime(
            title="Example",
            sources=["AniList"],
            voices=[person],
            voices_by_source={"AniList": [person]},
        )
        keyboard = people_keyboard(
            "token",
            anime,
            "voices",
            None,
            page=1,
            shown=1,
            total=1,
            max_page=1,
            locale="ru",
            source_names=["AniList"],
            first_page=1,
        )
        callbacks = [
            button.callback_data
            for row in keyboard.inline_keyboard
            for button in row
            if button.callback_data
        ]
        self.assertIn("as:token:voices:anilist:0", callbacks)


if __name__ == "__main__":
    unittest.main()
