from __future__ import annotations

import unittest
from unittest.mock import AsyncMock

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
        people = _merge_people(
            [
                [PersonCredit(name="Same Name", external_ids={"anilist": "1"})],
                [PersonCredit(name="Same Name", external_ids={"anilist": "2"})],
            ]
        )
        self.assertEqual(len(people), 2)

    def test_localization_credit_is_removed_as_a_whole(self) -> None:
        people = _merge_people(
            [
                [
                    PersonCredit(
                        name="Dub Person", roles=["Producer", "English ADR Director"]
                    )
                ]
            ],
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


class _ScreenshotSource:
    name = "Shikimori"

    async def get_details(self, identity: AnimeIdentity) -> AnimeRecord | None:
        source_id = str(identity.get("shikimori") or "")
        if not source_id:
            return None
        return AnimeRecord(
            source=self.name,
            source_id=source_id,
            titles={"romaji": "Screenshot Test"},
            external_ids={"shikimori": source_id},
            screenshots=[
                "https://example.invalid/1.jpg",
                "https://example.invalid/1.jpg",
                "https://example.invalid/2.jpg",
            ],
        )


class _PopularitySource:
    def __init__(self, name: str, *, list_users: int, scoring_users: int) -> None:
        self.name = name
        self.list_users = list_users
        self.scoring_users = scoring_users

    async def get_details(self, identity: AnimeIdentity) -> AnimeRecord | None:
        mal_id = str(identity.get("mal") or "")
        if not mal_id:
            return None
        return AnimeRecord(
            source=self.name,
            source_id=mal_id,
            titles={"english": "Popularity Test"},
            external_ids={"mal": mal_id},
            list_users=self.list_users,
            scoring_users=self.scoring_users,
            status_distribution={"completed": self.list_users},
        )


class AggregatorIdentityTests(unittest.IsolatedAsyncioTestCase):
    async def test_enriched_identity_reaches_sources_without_mutating_candidate(
        self,
    ) -> None:
        source = FakeSource()
        enriched = AnimeIdentity({"mal": "123", "shikimori": "456"})
        resolver = AsyncMock()
        resolver.enrich = AsyncMock(return_value=enriched)
        aggregator = AnimeAggregator((source,), identity_resolver=resolver)
        candidate = SearchCandidate(
            title="Test",
            aliases=["テスト"],
            external_ids={"mal": "123"},
        )

        anime = await aggregator.aggregate(candidate)

        resolver.enrich.assert_awaited()
        self.assertEqual(source.identities[0].external_ids, enriched.external_ids)
        self.assertEqual(candidate.external_ids, {"mal": "123"})
        self.assertEqual(anime.external_ids["shikimori"], "456")

    async def test_screenshots_remain_source_scoped_and_deduplicated(self) -> None:
        source = _ScreenshotSource()

        async def no_external_enrichment(
            identity: AnimeIdentity, titles: list[str]
        ) -> AnimeIdentity:
            return identity.copy()

        resolver = AsyncMock()
        resolver.enrich = AsyncMock(side_effect=no_external_enrichment)
        aggregator = AnimeAggregator((source,), identity_resolver=resolver)
        anime = await aggregator.aggregate(
            SearchCandidate(
                title="Screenshot Test",
                external_ids={"shikimori": "48316"},
            )
        )

        self.assertEqual(
            anime.screenshots_by_source["Shikimori"],
            [
                "https://example.invalid/1.jpg",
                "https://example.invalid/2.jpg",
            ],
        )

    async def test_popularity_statistics_remain_source_scoped(self) -> None:
        first = _PopularitySource("FirstDB", list_users=1000, scoring_users=700)
        second = _PopularitySource("SecondDB", list_users=250, scoring_users=120)

        async def no_external_enrichment(
            identity: AnimeIdentity, titles: list[str]
        ) -> AnimeIdentity:
            return identity.copy()

        resolver = AsyncMock()
        resolver.enrich = AsyncMock(side_effect=no_external_enrichment)
        aggregator = AnimeAggregator((first, second), identity_resolver=resolver)
        candidate = SearchCandidate(
            title="Popularity Test",
            external_ids={"mal": "20"},
        )

        anime = await aggregator.aggregate(candidate)

        self.assertEqual(anime.popularity_by_source["FirstDB"].list_users, 1000)
        self.assertEqual(anime.popularity_by_source["SecondDB"].list_users, 250)
        self.assertEqual(anime.popularity_by_source["FirstDB"].scoring_users, 700)
        self.assertEqual(anime.popularity_by_source["SecondDB"].scoring_users, 120)

    async def test_new_id_from_first_source_enables_second_pass_source(self) -> None:
        bridge = _AniListBridgeSource()
        mal = _MALSecondPassSource()

        async def no_external_enrichment(
            identity: AnimeIdentity, titles: list[str]
        ) -> AnimeIdentity:
            return identity.copy()

        resolver = AsyncMock()
        resolver.enrich = AsyncMock(side_effect=no_external_enrichment)
        aggregator = AnimeAggregator((bridge, mal), identity_resolver=resolver)
        candidate = SearchCandidate(
            title="Bridge",
            external_ids={"anilist": "10"},
        )

        anime = await aggregator.aggregate(candidate)

        self.assertEqual(anime.external_ids, {"anilist": "10", "mal": "20"})
        self.assertEqual(len(mal.identities), 2)
        self.assertIsNone(mal.identities[0].get("mal"))
        self.assertEqual(mal.identities[1].get("mal"), "20")
        self.assertEqual(candidate.external_ids, {"anilist": "10"})


if __name__ == "__main__":
    unittest.main()
