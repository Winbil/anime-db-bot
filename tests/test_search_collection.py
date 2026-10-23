from __future__ import annotations

import os
import unittest

from core.models import SearchCandidate, SearchPage
from services.search import SearchService, _relevance_score


class PagedProvider:
    def __init__(self, name: str, pages: dict[int, SearchPage]) -> None:
        self.name = name
        self.pages = pages
        self.calls: list[int] = []

    async def search(self, query: str, *, page: int, limit: int) -> SearchPage:
        self.calls.append(page)
        return self.pages.get(
            page,
            SearchPage(items=[], page=page, page_size=limit, has_next=False),
        )


def item(title: str, identity: dict[str, str], **kwargs) -> SearchCandidate:
    return SearchCandidate(title=title, external_ids=identity, **kwargs)


class SearchCollectionTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.previous = {
            key: os.environ.get(key)
            for key in (
                "SEARCH_CACHE_TTL_SECONDS",
                "SEARCH_RELEVANCE_THRESHOLD",
                "SEARCH_IRRELEVANT_TAIL_PAGES",
                "SEARCH_COLLECTION_MAX_ITEMS",
            )
        }
        os.environ["SEARCH_CACHE_TTL_SECONDS"] = "0"
        os.environ["SEARCH_RELEVANCE_THRESHOLD"] = "55"
        os.environ["SEARCH_IRRELEVANT_TAIL_PAGES"] = "1"
        os.environ["SEARCH_COLLECTION_MAX_ITEMS"] = "120"

    def tearDown(self) -> None:
        for key, value in self.previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    async def test_irrelevant_tail_stops_further_provider_pages(self) -> None:
        provider = PagedProvider(
            "Provider",
            {
                1: SearchPage(
                    items=[item("Naruto", {"x": "1"})],
                    page=1,
                    page_size=2,
                    has_next=True,
                ),
                2: SearchPage(
                    items=[item("Completely Different Show", {"x": "2"})],
                    page=2,
                    page_size=2,
                    has_next=True,
                ),
                3: SearchPage(
                    items=[item("Naruto Shippuden", {"x": "3"})],
                    page=3,
                    page_size=2,
                    has_next=False,
                ),
            },
        )
        service = SearchService((provider,))

        result = await service.collect("Naruto", page_size=2, max_pages=5)

        self.assertEqual(provider.calls, [1, 2])
        self.assertEqual([entry.title for entry in result.items], ["Naruto"])
        self.assertTrue(result.complete)

    async def test_hard_page_cap_marks_count_incomplete(self) -> None:
        provider = PagedProvider(
            "Provider",
            {
                1: SearchPage(
                    items=[item("Slime", {"x": "1"})],
                    page=1,
                    page_size=1,
                    has_next=True,
                ),
                2: SearchPage(
                    items=[item("Slime Season 2", {"x": "2"})],
                    page=2,
                    page_size=1,
                    has_next=True,
                ),
            },
        )
        service = SearchService((provider,))

        result = await service.collect("Slime", page_size=1, max_pages=2)

        self.assertEqual(provider.calls, [1, 2])
        self.assertEqual(len(result.items), 2)
        self.assertFalse(result.complete)

    async def test_collection_merges_same_anime_across_provider_pages(self) -> None:
        first = PagedProvider(
            "AniList",
            {
                1: SearchPage(
                    items=[
                        item(
                            "That Time I Got Reincarnated as a Slime",
                            {"anilist": "101280"},
                            romaji_title="Tensei shitara Slime Datta Ken",
                            posters=["https://example.invalid/a.jpg"],
                        )
                    ],
                    page=1,
                    page_size=10,
                    has_next=False,
                )
            },
        )
        second = PagedProvider(
            "Future",
            {
                1: SearchPage(
                    items=[
                        item(
                            "Tensei Shitara Slime Datta Ken",
                            {"future": "77"},
                            romaji_title="Tensei Shitara Slime Datta Ken",
                            posters=["https://example.invalid/b.jpg"],
                        )
                    ],
                    page=1,
                    page_size=10,
                    has_next=False,
                )
            },
        )
        service = SearchService((first, second))

        result = await service.collect("Tensei Slime")

        self.assertEqual(len(result.items), 1)
        self.assertEqual(
            result.items[0].external_ids,
            {"anilist": "101280", "future": "77"},
        )
        self.assertEqual(
            set(result.items[0].posters),
            {
                "https://example.invalid/a.jpg",
                "https://example.invalid/b.jpg",
            },
        )

    async def test_collection_ranks_exact_title_before_related_title(self) -> None:
        provider = PagedProvider(
            "Provider",
            {
                1: SearchPage(
                    items=[
                        item("Naruto Shippuden", {"x": "2"}),
                        item("Naruto", {"x": "1"}),
                    ],
                    page=1,
                    page_size=10,
                    has_next=False,
                )
            },
        )
        service = SearchService((provider,))

        result = await service.collect("Naruto")

        self.assertEqual(
            [entry.title for entry in result.items],
            ["Naruto", "Naruto Shippuden"],
        )

    def test_relevance_policy_prefers_exact_prefix_and_tokens(self) -> None:
        exact = item(
            "That Time I Got Reincarnated as a Slime",
            {"mal": "1"},
            aliases=["Tensei shitara Slime Datta Ken"],
        )
        related = item("Naruto Shippuden", {"mal": "2"})
        unrelated = item("Frieren: Beyond Journey's End", {"mal": "3"})

        self.assertEqual(
            _relevance_score("Tensei shitara Slime Datta Ken", exact),
            100,
        )
        self.assertGreaterEqual(_relevance_score("Naruto", related), 90)
        self.assertLess(_relevance_score("Naruto", unrelated), 55)

    def test_common_english_word_does_not_create_false_positive(self) -> None:
        unrelated = item(
            "The Iceblade Sorcerer Shall Rule the World",
            {"mal": "1"},
        )

        self.assertLess(
            _relevance_score("The Eminence In Shadow", unrelated),
            55,
        )

    def test_short_russian_preposition_does_not_create_false_positive(self) -> None:
        unrelated = item("Восхождение Героя Щита", {"shikimori": "1"})

        self.assertLess(
            _relevance_score("Восхождение в тени", unrelated),
            55,
        )

    def test_naruto_does_not_match_unrelated_harukanaru_title(self) -> None:
        unrelated = item(
            "Harukanaru Toki no Naka de: Hachiyou Shou",
            {"mal": "247"},
        )

        self.assertLess(_relevance_score("Naruto", unrelated), 55)

    def test_relevance_policy_preserves_native_script_aliases(self) -> None:
        candidate = item(
            "That Time I Got Reincarnated as a Slime",
            {"anilist": "101280"},
            aliases=["転生したらスライムだった件"],
        )

        self.assertEqual(
            _relevance_score("転生したらスライムだった件", candidate),
            100,
        )


if __name__ == "__main__":
    unittest.main()
