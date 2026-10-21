from __future__ import annotations

import os
import unittest

from core.models import SearchCandidate, SearchPage
from services.search import SearchService


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


if __name__ == "__main__":
    unittest.main()
