from __future__ import annotations

import unittest

from bots.telegram.card.renderer import anime_sections
from core.models import AggregatedAnime
from core.source_names import MAL_SOURCE_NAME


class CardSourceIdTests(unittest.TestCase):
    def test_main_card_shows_only_ids_for_contributing_metadata_sources(self) -> None:
        anime = AggregatedAnime(
            title="Example",
            sources=[MAL_SOURCE_NAME, "AniList"],
            external_ids={
                "mal": "100",
                "anilist": "200",
                "shikimori": "300",
                "anidb": "400",
            },
        )

        main = anime_sections(anime, locale="en")["main"]

        self.assertIn("MAL: 100", main)
        self.assertIn("ANILIST: 200", main)
        self.assertNotIn("SHIKIMORI: 300", main)
        self.assertNotIn("ANIDB: 400", main)

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


if __name__ == "__main__":
    unittest.main()
