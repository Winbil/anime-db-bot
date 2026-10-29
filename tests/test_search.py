from __future__ import annotations

import os
import unittest

from core.models import SearchCandidate, SearchPage
from services.search.service import SearchService


class FakeProvider:
    def __init__(self, name: str, items: list[SearchCandidate], *, fail: bool = False) -> None:
        self.name = name
        self.items = items
        self.fail = fail
        self.calls = 0

    async def search(self, query: str, *, page: int, limit: int) -> SearchPage:
        self.calls += 1
        if self.fail:
            raise RuntimeError("temporary failure")
        return SearchPage(
            items=list(self.items),
            page=page,
            page_size=limit,
            has_next=False,
        )


def candidate(mal_id: int, title: str) -> SearchCandidate:
    return SearchCandidate(
        title=title,
        external_ids={"mal": str(mal_id)},
    )


class SearchServiceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.old_ttl = os.environ.get("SEARCH_CACHE_TTL_SECONDS")
        os.environ["SEARCH_CACHE_TTL_SECONDS"] = "21600"

    def tearDown(self) -> None:
        if self.old_ttl is None:
            os.environ.pop("SEARCH_CACHE_TTL_SECONDS", None)
        else:
            os.environ["SEARCH_CACHE_TTL_SECONDS"] = self.old_ttl

    async def test_merged_page_never_exceeds_page_size(self) -> None:
        first = FakeProvider(
            "Shikimori",
            [candidate(index, f"A {index}") for index in range(1, 11)],
        )
        second = FakeProvider(
            "MyAnimeList",
            [candidate(index, f"B {index}") for index in range(11, 21)],
        )
        service = SearchService((first, second))

        page = await service.search("anime", page=1, page_size=10)

        self.assertEqual(len(page.items), 10)
        self.assertTrue(page.has_next)

    async def test_successful_page_is_cached(self) -> None:
        provider = FakeProvider("Shikimori", [candidate(1, "One")])
        service = SearchService((provider,))

        await service.search("one", page=1, page_size=10)
        await service.search("one", page=1, page_size=10)

        self.assertEqual(provider.calls, 1)

    async def test_partial_failure_is_not_cached(self) -> None:
        good = FakeProvider("Shikimori", [candidate(1, "One")])
        bad = FakeProvider("MyAnimeList", [], fail=True)
        service = SearchService((good, bad))

        first = await service.search("one", page=1, page_size=10)
        second = await service.search("one", page=1, page_size=10)

        self.assertIn("MyAnimeList", first.errors)
        self.assertIn("MyAnimeList", second.errors)
        self.assertEqual(good.calls, 2)
        self.assertEqual(bad.calls, 2)

    async def test_result_without_mal_id_is_not_dropped(self) -> None:
        provider = FakeProvider(
            "AniList",
            [SearchCandidate(title="AniList only", external_ids={"anilist": "10"})],
        )
        service = SearchService((provider,))

        page = await service.search("anilist only")

        self.assertEqual(len(page.items), 1)
        self.assertEqual(page.items[0].external_ids, {"anilist": "10"})

    async def test_results_merge_by_shared_non_mal_id(self) -> None:
        first = FakeProvider(
            "AniList",
            [
                SearchCandidate(
                    title="First title",
                    aliases=["Alias A"],
                    external_ids={"anilist": "10"},
                )
            ],
        )
        second = FakeProvider(
            "FutureProvider",
            [
                SearchCandidate(
                    title="Second title",
                    aliases=["Alias B"],
                    external_ids={"anilist": "10", "futuredb": "50"},
                )
            ],
        )
        service = SearchService((first, second))

        page = await service.search("test")

        self.assertEqual(len(page.items), 1)
        self.assertEqual(
            page.items[0].external_ids,
            {"anilist": "10", "futuredb": "50"},
        )
        self.assertIn("Alias A", page.items[0].aliases)
        self.assertIn("Alias B", page.items[0].aliases)

    async def test_identity_merge_is_transitive_across_database_edges(self) -> None:
        first = FakeProvider(
            "ProviderA",
            [SearchCandidate(title="A", external_ids={"anilist": "10"})],
        )
        bridge = FakeProvider(
            "ProviderBridge",
            [
                SearchCandidate(
                    title="Bridge",
                    external_ids={"anilist": "10", "shikimori": "30"},
                )
            ],
        )
        third = FakeProvider(
            "ProviderC",
            [SearchCandidate(title="C", external_ids={"shikimori": "30"})],
        )
        service = SearchService((first, bridge, third))

        page = await service.search("test")

        self.assertEqual(len(page.items), 1)
        self.assertEqual(
            page.items[0].external_ids,
            {"anilist": "10", "shikimori": "30"},
        )

    async def test_conflicting_ids_are_not_merged(self) -> None:
        first = FakeProvider(
            "ProviderA",
            [
                SearchCandidate(
                    title="A",
                    external_ids={"mal": "20", "anilist": "10"},
                )
            ],
        )
        second = FakeProvider(
            "ProviderB",
            [
                SearchCandidate(
                    title="B",
                    external_ids={"mal": "20", "anilist": "11"},
                )
            ],
        )
        service = SearchService((first, second))

        page = await service.search("test")

        self.assertEqual(len(page.items), 2)

    async def test_weak_bridge_cannot_transitively_hide_id_conflict(self) -> None:
        first = FakeProvider(
            "ProviderA",
            [
                SearchCandidate(
                    title="A",
                    external_ids={"mal": "20", "anilist": "10"},
                )
            ],
        )
        weak_bridge = FakeProvider(
            "ProviderBridge",
            [SearchCandidate(title="Bridge", external_ids={"mal": "20"})],
        )
        conflicting = FakeProvider(
            "ProviderC",
            [
                SearchCandidate(
                    title="C",
                    external_ids={"mal": "20", "anilist": "11"},
                )
            ],
        )
        service = SearchService((first, weak_bridge, conflicting))

        page = await service.search("test")

        self.assertEqual(len(page.items), 2)
        self.assertEqual(
            {item.external_ids.get("anilist") for item in page.items},
            {"10", "11"},
        )

    async def test_second_layer_merges_independent_ids_by_exact_romaji(self) -> None:
        anilist = FakeProvider(
            "AniList",
            [
                SearchCandidate(
                    title="That Time I Got Reincarnated as a Slime",
                    romaji_title="Tensei shitara Slime Datta Ken",
                    year=2018,
                    external_ids={"anilist": "101280"},
                )
            ],
        )
        future = FakeProvider(
            "AniLiberty",
            [
                SearchCandidate(
                    title="О моём перерождении в слизь",
                    romaji_title="Tensei Shitara Slime Datta Ken",
                    year=2018,
                    external_ids={"aniliberty": "777"},
                )
            ],
        )
        service = SearchService((anilist, future))

        page = await service.search("slime")

        self.assertEqual(len(page.items), 1)
        self.assertEqual(
            page.items[0].external_ids,
            {"anilist": "101280", "aniliberty": "777"},
        )
        self.assertEqual(
            page.items[0].romaji_title,
            "Tensei shitara Slime Datta Ken",
        )

    async def test_romaji_layer_normalizes_punctuation_and_spacing(self) -> None:
        first = FakeProvider(
            "ProviderA",
            [
                SearchCandidate(
                    title="Title A",
                    romaji_title="Kono Subarashii Sekai ni Shukufuku wo!",
                    external_ids={"a": "1"},
                )
            ],
        )
        second = FakeProvider(
            "ProviderB",
            [
                SearchCandidate(
                    title="Title B",
                    romaji_title="  Kono Subarashii Sekai ni Shukufuku wo  ",
                    external_ids={"b": "2"},
                )
            ],
        )
        service = SearchService((first, second))

        page = await service.search("konosuba")

        self.assertEqual(len(page.items), 1)
        self.assertEqual(page.items[0].external_ids, {"a": "1", "b": "2"})

    async def test_romaji_layer_does_not_merge_different_known_years(self) -> None:
        first = FakeProvider(
            "ProviderA",
            [
                SearchCandidate(
                    title="Original",
                    romaji_title="Same Name",
                    year=2001,
                    external_ids={"a": "1"},
                )
            ],
        )
        second = FakeProvider(
            "ProviderB",
            [
                SearchCandidate(
                    title="Remake",
                    romaji_title="Same Name",
                    year=2026,
                    external_ids={"b": "2"},
                )
            ],
        )
        service = SearchService((first, second))

        page = await service.search("same name")

        self.assertEqual(len(page.items), 2)

    async def test_romaji_layer_never_overrides_same_database_id_conflict(self) -> None:
        first = FakeProvider(
            "ProviderA",
            [
                SearchCandidate(
                    title="First",
                    romaji_title="Shared Romaji",
                    year=2020,
                    external_ids={"anilist": "10"},
                )
            ],
        )
        second = FakeProvider(
            "ProviderB",
            [
                SearchCandidate(
                    title="Second",
                    romaji_title="Shared Romaji",
                    year=2020,
                    external_ids={"anilist": "11", "futuredb": "20"},
                )
            ],
        )
        service = SearchService((first, second))

        page = await service.search("shared")

        self.assertEqual(len(page.items), 2)
        self.assertEqual(
            {item.external_ids.get("anilist") for item in page.items},
            {"10", "11"},
        )

    async def test_shared_id_layer_wins_even_when_romaji_differs(self) -> None:
        first = FakeProvider(
            "ProviderA",
            [
                SearchCandidate(
                    title="First",
                    romaji_title="Romanization A",
                    external_ids={"mal": "100"},
                )
            ],
        )
        second = FakeProvider(
            "ProviderB",
            [
                SearchCandidate(
                    title="Second",
                    romaji_title="Romanization B",
                    external_ids={"mal": "100", "futuredb": "200"},
                )
            ],
        )
        service = SearchService((first, second))

        page = await service.search("test")

        self.assertEqual(len(page.items), 1)
        self.assertEqual(page.items[0].external_ids, {"mal": "100", "futuredb": "200"})


if __name__ == "__main__":
    unittest.main()
