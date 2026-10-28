from __future__ import annotations

import unittest

from bots.telegram.card.characters import _keyboard as character_keyboard
from bots.telegram.card.characters import _page_text as character_page_text
from bots.telegram.card.state import AnimeCardSession
from bots.telegram.people_portraits import _keyboard as people_keyboard
from bots.telegram.people_portraits import _page_text as people_page_text
from core.models import AggregatedAnime, CharacterRecord, PersonCredit


class EmptyPortraitPageRoutingTests(unittest.TestCase):
    def test_staff_and_voices_skip_empty_zero_page(self) -> None:
        for section in ("staff", "voices"):
            with self.subTest(section=section):
                person = PersonCredit(
                    name="Portrait Person",
                    roles=["voice_actor"],
                    portraits={"AniList": ["https://img.example/person.jpg"]},
                )
                anime = AggregatedAnime(title="Example", sources=["AniList"])
                setattr(anime, section, [person])
                setattr(anime, f"{section}_by_source", {"AniList": [person]})

                for source in (None, "AniList"):
                    with self.subTest(section=section, source=source):
                        content, urls, shown, total, page = people_page_text(
                            anime,
                            section,
                            source,
                            0,
                            locale="ru",
                        )

                        self.assertEqual(page, 1)
                        self.assertEqual(urls, ["https://img.example/person.jpg"])
                        self.assertIn("Portrait Person", content)
                        self.assertEqual((shown, total), (1, 1))

                        keyboard = people_keyboard(
                            "token",
                            anime,
                            section,
                            None,
                            page,
                            shown,
                            total,
                            1,
                            locale="ru",
                            source_names=["AniList"],
                            first_page=1,
                        )
                        nav_callbacks = [
                            button.callback_data
                            for button in keyboard.inline_keyboard[0]
                        ]
                        self.assertNotIn(f"av:token:{section}:0", nav_callbacks)

    def test_people_keep_zero_page_when_portraitless_entries_exist(self) -> None:
        portraitless = PersonCredit(name="No Portrait", roles=["voice_actor"])
        portrait = PersonCredit(
            name="Portrait Person",
            roles=["voice_actor"],
            portraits={"AniList": ["https://img.example/person.jpg"]},
        )
        anime = AggregatedAnime(
            title="Example",
            sources=["AniList"],
            voices=[portraitless, portrait],
            voices_by_source={"AniList": [portraitless, portrait]},
        )

        content, urls, shown, total, page = people_page_text(
            anime,
            "voices",
            None,
            0,
            locale="ru",
        )

        self.assertEqual(page, 0)
        self.assertEqual(urls, [])
        self.assertIn("No Portrait", content)
        self.assertEqual((shown, total), (1, 2))

    def test_characters_skip_empty_zero_page(self) -> None:
        character = CharacterRecord(
            name="Cid Kagenou",
            role="main",
            portraits={"AniList": ["https://img.example/cid.jpg"]},
        )
        anime = AggregatedAnime(
            title="Shadow",
            sources=["AniList"],
            characters=[character],
            characters_by_source={"AniList": [character]},
        )
        session = AnimeCardSession(anime=anime, owner_user_id=1, characters_loaded=True)

        for source in (None, "AniList"):
            with self.subTest(source=source):
                content, urls, shown, total, page = character_page_text(
                    session,
                    source,
                    0,
                    locale="ru",
                )

                self.assertEqual(page, 1)
                self.assertEqual(urls, ["https://img.example/cid.jpg"])
                self.assertIn("Cid Kagenou", content)
                self.assertEqual((shown, total), (1, 1))

                keyboard = character_keyboard(
                    "token",
                    [("anilist", "AniList")],
                    None,
                    page,
                    shown,
                    total,
                    1,
                    locale="ru",
                    first_page=1,
                )
                nav_callbacks = [
                    button.callback_data for button in keyboard.inline_keyboard[0]
                ]
                self.assertNotIn("av:token:characters:0", nav_callbacks)

    def test_characters_keep_zero_page_when_portraitless_entries_exist(self) -> None:
        portraitless = CharacterRecord(name="No Portrait", role="supporting")
        portrait = CharacterRecord(
            name="Cid Kagenou",
            role="main",
            portraits={"AniList": ["https://img.example/cid.jpg"]},
        )
        anime = AggregatedAnime(
            title="Shadow",
            sources=["AniList"],
            characters=[portraitless, portrait],
            characters_by_source={"AniList": [portraitless, portrait]},
        )
        session = AnimeCardSession(anime=anime, owner_user_id=1, characters_loaded=True)

        content, urls, shown, total, page = character_page_text(
            session,
            None,
            0,
            locale="ru",
        )

        self.assertEqual(page, 0)
        self.assertEqual(urls, [])
        self.assertIn("No Portrait", content)
        self.assertEqual((shown, total), (1, 2))


if __name__ == "__main__":
    unittest.main()
