from __future__ import annotations

import os
import unittest

from core.models import SearchCandidate, SearchResultSet
from services.search.expansion import expand_text_search, expansion_queries


class FakeSearchService:
    def __init__(self, responses: dict[str, SearchResultSet]) -> None:
        self.responses = responses
        self.calls: list[tuple[str, int | None]] = []

    async def collect(self, query: str, *, max_pages: int | None = None):
        self.calls.append((query, max_pages))
        return self.responses.get(query, SearchResultSet(items=[]))


class FakeDirectLookup:
    def __init__(self, enriched: SearchCandidate) -> None:
        self.enriched = enriched
        self.calls: list[SearchCandidate] = []

    async def enrich_candidate(self, candidate: SearchCandidate) -> SearchCandidate:
        self.calls.append(candidate)
        return self.enriched


class SearchExpansionTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.previous = {
            key: os.environ.get(key)
            for key in (
                "SEARCH_EXPANSION_MAX_SEEDS",
                "SEARCH_EXPANSION_MAX_QUERIES",
                "SEARCH_EXPANSION_MAX_PAGES",
                "SEARCH_COLLECTION_MAX_ITEMS",
            )
        }
        os.environ["SEARCH_EXPANSION_MAX_SEEDS"] = "1"
        os.environ["SEARCH_EXPANSION_MAX_QUERIES"] = "1"
        os.environ["SEARCH_EXPANSION_MAX_PAGES"] = "2"
        os.environ["SEARCH_COLLECTION_MAX_ITEMS"] = "120"

    def tearDown(self) -> None:
        for key, value in self.previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def test_latin_query_prefers_confirmed_cyrillic_alias(self) -> None:
        candidate = SearchCandidate(
            title="Example Hero",
            romaji_title="Example Hero no Monogatari",
            aliases=["Пример героя", "Example Hero"],
            external_ids={"mal": "10", "shikimori": "20"},
        )

        self.assertEqual(
            expansion_queries("Example Hero", [candidate], limit=1),
            ["Пример героя"],
        )

    def test_cyrillic_query_prefers_confirmed_latin_alias(self) -> None:
        candidate = SearchCandidate(
            title="Пример героя",
            romaji_title="Example Hero no Monogatari",
            aliases=["Example Hero", "Пример героя"],
            external_ids={"mal": "10", "shikimori": "20"},
        )

        self.assertEqual(
            expansion_queries("Пример героя", [candidate], limit=1),
            ["Example Hero no Monogatari"],
        )

    async def test_expansion_adds_alternate_language_results_after_primary_results(self) -> None:
        primary = SearchCandidate(
            title="Example Hero",
            aliases=[],
            external_ids={"mal": "10"},
        )
        enriched = SearchCandidate(
            title="Example Hero",
            aliases=["Пример героя"],
            external_ids={"mal": "10", "shikimori": "20"},
        )
        side_story = SearchCandidate(
            title="Пример героя: Мини-истории",
            aliases=["Example Hero Mini Stories"],
            external_ids={"shikimori": "21"},
        )
        service = FakeSearchService(
            {
                "Пример героя": SearchResultSet(
                    items=[enriched, side_story],
                    complete=True,
                )
            }
        )
        direct_lookup = FakeDirectLookup(enriched)

        result = await expand_text_search(
            service=service,
            direct_lookup=direct_lookup,
            query="Example Hero",
            initial=SearchResultSet(items=[primary], complete=True),
        )

        self.assertEqual(service.calls, [("Пример героя", 2)])
        self.assertEqual(len(direct_lookup.calls), 1)
        self.assertEqual(len(result.items), 2)
        self.assertEqual(result.items[0].external_ids, {"mal": "10", "shikimori": "20"})
        self.assertEqual(result.items[1].external_ids, {"shikimori": "21"})
        self.assertEqual(result.items[1].title, "Пример героя: Мини-истории")


if __name__ == "__main__":
    unittest.main()