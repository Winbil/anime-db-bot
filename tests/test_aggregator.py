from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, patch

from core.models import AggregatedAnime, AnimeRecord, PersonCredit, SearchCandidate
from services.aggregator import AnimeAggregator, _merge_people


class FakeSource:
    name = "Fake"

    def __init__(self) -> None:
        self.known_ids: dict[str, str] | None = None

    async def get_details(
        self,
        mal_id: str,
        known_ids: dict[str, str],
    ) -> AnimeRecord | None:
        self.known_ids = dict(known_ids)
        return AnimeRecord(
            source=self.name,
            source_id="fake",
            titles={"english": "Test"},
            external_ids={"mal": mal_id},
        )


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


class AggregatorCrossIdTests(unittest.IsolatedAsyncioTestCase):
    async def test_missing_shikimori_id_is_resolved_before_sources_run(self) -> None:
        source = FakeSource()
        aggregator = AnimeAggregator((source,))
        candidate = SearchCandidate(
            title="Test",
            aliases=["テスト"],
            external_ids={"mal": "123"},
        )

        with patch(
            "services.aggregator.resolve_shikimori_id",
            new=AsyncMock(return_value="456"),
        ) as resolver:
            anime = await aggregator.aggregate(candidate)

        resolver.assert_awaited_once_with("123", ["Test", "テスト"])
        self.assertIsNotNone(source.known_ids)
        assert source.known_ids is not None
        self.assertEqual(source.known_ids["shikimori"], "456")
        self.assertEqual(candidate.external_ids["shikimori"], "456")
        self.assertEqual(anime.external_ids["shikimori"], "456")


if __name__ == "__main__":
    unittest.main()
