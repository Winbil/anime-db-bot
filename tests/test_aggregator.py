from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, patch

from core.identity import AnimeIdentity
from core.models import AggregatedAnime, AnimeRecord, PersonCredit, SearchCandidate
from services.aggregator import _merge_people
from services.identity_aggregator import AnimeAggregator


class FakeSource:
    name = "Fake"

    def __init__(self) -> None:
        self.identities: list[AnimeIdentity] = []

    async def get_details(self, identity: AnimeIdentity) -> AnimeRecord | None:
        self.identities.append(identity.copy())
        return AnimeRecord(
            source=self.name,
            source_id="fake",
            titles={"english": "Test"},
            external_ids=dict(identity.external_ids),
        )


class _AniListBridgeSource:
    name = "AniList"

    async def get_details(self, identity: AnimeIdentity) -> AnimeRecord | None:
        if identity.get("anilist") != "10":
            return None
        return AnimeRecord(
            source=self.name,
            source_id="10",
            titles={"english": "Bridge"},
            external_ids={"anilist": "10", "mal": "20"},
        )


class _MALSecondPassSource:
    name = "MyAnimeList"

    def __init__(self) -> None:
        self.identities: list[AnimeIdentity] = []

    async def get_details(self, identity: AnimeIdentity) -> AnimeRecord | None:
        self.identities.append(identity.copy())
        if identity.get("mal") != "20":
            return None
        return AnimeRecord(
            source=self.name,
            source_id="20",
            titles={"romaji": "Bridge"},
            external_ids={"mal": "20"},
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
        self.assertEqual(set(anime.voices[0].portraits), {"Shikimori", "AniList"})
        self.assertEqual(
            anime.voices[0].external_ids,
            {"shikimori": "321", "anilist": "123"},
        )


class AggregatorIdentityTests(unittest.IsolatedAsyncioTestCase):
    async def test_enriched_identity_reaches_sources_without_mutating_candidate(self) -> None:
        source = FakeSource()
        aggregator = AnimeAggregator((source,))
        candidate = SearchCandidate(
            title="Test",
            aliases=["テスト"],
            external_ids={"mal": "123"},
        )
        enriched = AnimeIdentity({"mal": "123", "shikimori": "456"})

        with patch(
            "services.identity_aggregator.enrich_identity",
            new=AsyncMock(return_value=enriched),
        ) as resolver:
            anime = await aggregator.aggregate(candidate)

        resolver.assert_awaited()
        self.assertEqual(source.identities[0].external_ids, enriched.external_ids)
        self.assertEqual(candidate.external_ids, {"mal": "123"})
        self.assertEqual(anime.external_ids["shikimori"], "456")

    async def test_new_id_from_first_source_enables_second_pass_source(self) -> None:
        bridge = _AniListBridgeSource()
        mal = _MALSecondPassSource()
        aggregator = AnimeAggregator((bridge, mal))
        candidate = SearchCandidate(
            title="Bridge",
            external_ids={"anilist": "10"},
        )

        async def no_external_enrichment(identity: AnimeIdentity, titles: list[str]) -> AnimeIdentity:
            return identity.copy()

        with patch(
            "services.identity_aggregator.enrich_identity",
            new=AsyncMock(side_effect=no_external_enrichment),
        ):
            anime = await aggregator.aggregate(candidate)

        self.assertEqual(anime.external_ids, {"anilist": "10", "mal": "20"})
        self.assertEqual(len(mal.identities), 2)
        self.assertIsNone(mal.identities[0].get("mal"))
        self.assertEqual(mal.identities[1].get("mal"), "20")
        self.assertEqual(candidate.external_ids, {"anilist": "10"})


if __name__ == "__main__":
    unittest.main()
