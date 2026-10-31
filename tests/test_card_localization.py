from __future__ import annotations

import unittest

from bots.telegram.card.views.renderer import anime_sections, display_anime_title
from core.models import AggregatedAnime, BroadcastSlot, PersonCredit


class CardLocalizationTests(unittest.TestCase):
    def _sample(self) -> AggregatedAnime:
        return AggregatedAnime(
            title="Tensei Shitara Slime Datta Ken",
            titles={
                "russian": "О моём перерождении в слизь",
                "english": "That Time I Got Reincarnated as a Slime",
                "romaji": "Tensei Shitara Slime Datta Ken",
                "japanese": "転生したらスライムだった件",
                "german": "Meine Wiedergeburt als Schleim in einer anderen Welt",
                "spanish": "Aquella vez que me convertí en Slime",
                "french": "Moi, quand je me réincarne en Slime",
                "italian": "Vita da slime",
            },
            kind="tv",
            status="airing",
            rating="pg_13",
            season="spring",
            season_year=2026,
            episodes_total=24,
            episodes_aired=12,
            duration_minutes=24,
            genres=["fantasy", "isekai"],
            source_materials=["light_novel"],
            broadcasts=[BroadcastSlot(weekday="monday", time="20:00")],
            staff=[
                PersonCredit(
                    name="Jun Fukuyama",
                    aliases=["Дзюн Фукуяма", "福山 潤"],
                    roles=["director"],
                )
            ],
            voices=[
                PersonCredit(
                    name="Miho Okasaki",
                    aliases=["Михо Окасаки", "岡咲 美保"],
                    roles=["voice_of::Rimuru Tempest"],
                )
            ],
        )

    def test_same_domain_model_renders_russian_and_english(self) -> None:
        anime = self._sample()
        ru = anime_sections(anime, locale="ru")
        en = anime_sections(anime, locale="en")

        self.assertEqual(
            display_anime_title(anime, "ru"), "О моём перерождении в слизь"
        )
        self.assertEqual(
            display_anime_title(anime, "en"),
            "That Time I Got Reincarnated as a Slime",
        )

        self.assertIn("Статус: выходит", ru["main"])
        self.assertIn("Сезон: Весна 2026", ru["main"])
        self.assertIn("Жанры: Фэнтези, Исекай", ru["main"])
        self.assertIn("Первоисточник: Ранобэ", ru["main"])
        self.assertIn("Расписание: Понедельник 20:00", ru["main"])

        self.assertIn("Status: Airing", en["main"])
        self.assertIn("Season: Spring 2026", en["main"])
        self.assertIn("Genres: Fantasy, Isekai", en["main"])
        self.assertIn("Source material: Light Novel", en["main"])
        self.assertIn("Schedule: Monday 20:00", en["main"])

    def test_western_locales_prefer_matching_localized_anime_title(self) -> None:
        anime = self._sample()
        expected = {
            "de": "Meine Wiedergeburt als Schleim in einer anderen Welt",
            "es": "Aquella vez que me convertí en Slime",
            "fr": "Moi, quand je me réincarne en Slime",
            "it": "Vita da slime",
        }
        for locale, title in expected.items():
            with self.subTest(locale=locale):
                self.assertEqual(display_anime_title(anime, locale), title)

    def test_people_names_and_roles_are_rendered_once_per_locale(self) -> None:
        anime = self._sample()
        ru = anime_sections(anime, locale="ru")
        en = anime_sections(anime, locale="en")

        self.assertIn("Дзюн Фукуяма (Jun Fukuyama, 福山 潤) — Режиссёр", ru["staff"])
        self.assertIn("Jun Fukuyama (福山 潤) — Director", en["staff"])
        self.assertIn(
            "Михо Окасаки (Miho Okasaki, 岡咲 美保) — Озвучка: Rimuru Tempest",
            ru["voices"],
        )
        self.assertIn("Miho Okasaki (岡咲 美保) — Voice: Rimuru Tempest", en["voices"])
        self.assertNotIn("Дзюн Фукуяма (Jun Fukuyama, Дзюн Фукуяма", ru["staff"])


if __name__ == "__main__":
    unittest.main()
