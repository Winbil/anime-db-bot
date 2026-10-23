from __future__ import annotations

import unittest

from bots.telegram.card.renderer import anime_sections, main_rich, rich_view
from core.models import AggregatedAnime, BroadcastSlot


class CardRichLayoutTests(unittest.TestCase):
    def _sample(self) -> AggregatedAnime:
        return AggregatedAnime(
            title="Tensei Shitara Slime Datta Ken",
            titles={
                "russian": "О моём перерождении в слизь",
                "english": "That Time I Got Reincarnated as a Slime",
                "romaji": "Tensei Shitara Slime Datta Ken",
                "japanese": "転生したらスライムだった件",
            },
            synonyms=["Tensura"],
            kind="tv",
            status="airing",
            rating="pg_13",
            season="spring",
            season_year=2026,
            episodes_total=24,
            episodes_aired=12,
            duration_minutes=24,
            aired_on="2026-04-01",
            released_on="2026-09-16",
            broadcasts=[BroadcastSlot(weekday="monday", time="20:00")],
            genres=["fantasy", "isekai"],
            source_materials=["light_novel"],
            studios=["8bit"],
            score_average=8.6,
            score_sources_count=2,
            scores={"MyAnimeList": 8.5, "AniList": 8.7},
            rank=120,
            popularity_rank=35,
            list_users=123456,
            scoring_users=98765,
            favorites=4321,
            sources=["MyAnimeList", "AniList", "Shikimori"],
            external_ids={"mal": "37430", "anilist": "101280", "shikimori": "37430"},
            posters=["https://example.com/poster.jpg"],
        )

    def test_main_rich_uses_native_tables_and_places_actions_before_data(self) -> None:
        anime = self._sample()
        main_text = anime_sections(anime, locale="ru")["main"]
        rich_message = main_rich("card-token", anime, main_text, locale="ru")

        html = rich_message.html or ""
        self.assertIn("<table bordered striped compact>", html)
        self.assertIn("<caption><b>Основное</b></caption>", html)
        self.assertIn("<caption><b>Выход</b></caption>", html)
        self.assertIn("<caption><b>Производство</b></caption>", html)
        self.assertIn("<caption><b>Оценка и популярность</b></caption>", html)
        self.assertIn("<caption><b>Источники</b></caption>", html)
        self.assertIn(">Статус</th>", html)
        self.assertIn(">выходит</td>", html)

        first_table = html.index("<table")
        for section in ("description", "staff", "voices", "titles", "links"):
            self.assertLess(
                html.index(f"av:card-token:{section}:0"),
                first_table,
                msg=f"{section} quick action must stay above the data tables",
            )

        self.assertIn("<tg-button-row", html)
        self.assertNotIn("выбрать источник", html)
        self.assertNotIn("нажмите, чтобы открыть", html)

    def test_titles_section_uses_table_for_structured_title_variants(self) -> None:
        anime = self._sample()
        titles_text = anime_sections(anime, locale="ru")["titles"]
        rich_message = rich_view(
            "card-token",
            anime,
            "titles",
            titles_text,
            locale="ru",
        )

        html = rich_message.html or ""
        self.assertIn("<table bordered striped compact>", html)
        self.assertIn("<caption><b>Названия</b></caption>", html)
        self.assertIn(">Русское</th>", html)
        self.assertIn(">О моём перерождении в слизь</td>", html)
        self.assertIn(">Оригинальное / romaji</th>", html)
        self.assertIn(">Tensei Shitara Slime Datta Ken</td>", html)
        self.assertIn(">Синонимы</th>", html)
        self.assertIn(">Tensura</td>", html)


if __name__ == "__main__":
    unittest.main()
