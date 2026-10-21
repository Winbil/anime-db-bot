from __future__ import annotations

import unittest

from core.models import AggregatedAnime, PersonCredit
from services.aggregator import AnimeAggregator, _merge_people


class AggregatorPeopleTests(unittest.TestCase):
    def test_conflicting_same_source_ids_do_not_merge_by_name(self) -> None:
        people = _merge_people([
            [PersonCredit(name="Same Name", external_ids={"anilist": "1"})],
            [PersonCredit(name="Same Name", external_ids={"anilist": "2"})],
        ])

        self.assertEqual(len(people), 2)

    def test_localization_credit_is_removed_as_a_whole(self) -> None:
        people = _merge_people(
            [[PersonCredit(name="Dub Person", roles=["Producer", "English ADR Director"])]],
            drop_localization_roles=True,
        )

        self.assertEqual(people, [])

    def test_lazy_source_merge_preserves_portrait_provenance(self) -> None:
        aggregator = AnimeAggregator(())
        anime = AggregatedAnime(
            title="Test",
            sources=["Shikimori", "AniList"],
            voices_by_source={
                "AniList": [
                    PersonCredit(
                        name="Miho Okasaki",
                        aliases=["岡咲 美保"],
                        external_ids={"anilist": "123"},
                        portraits={"AniList": ["https://example.invalid/anilist.jpg"]},
                    )
                ]
            },
            voices=[
                PersonCredit(
                    name="Miho Okasaki",
                    aliases=["岡咲 美保"],
                    external_ids={"anilist": "123"},
                    portraits={"AniList": ["https://example.invalid/anilist.jpg"]},
                )
            ],
        )

        aggregator.merge_people_source(
            anime,
            source_name="Shikimori",
            section="voices",
            people=[
                PersonCredit(
                    name="Miho Okasaki",
                    aliases=["岡咲 美保"],
                    external_ids={"shikimori": "321"},
                    portraits={"Shikimori": ["https://example.invalid/shikimori.jpg"]},
                )
            ],
        )

        self.assertIn("Shikimori", anime.voices_by_source)
        self.assertEqual(len(anime.voices), 1)
        self.assertEqual(
            set(anime.voices[0].portraits),
            {"Shikimori", "AniList"},
        )
        self.assertEqual(
            anime.voices[0].external_ids,
            {"shikimori": "321", "anilist": "123"},
        )


if __name__ == "__main__":
    unittest.main()
