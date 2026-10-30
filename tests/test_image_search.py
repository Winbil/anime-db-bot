from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

import httpx

from core.image_search import (
    ImageSearchAvailability,
    ImageSearchInput,
    ImageSearchMatch,
)
from core.models import SearchCandidate, SearchResultSet
from services.search.image_quota import SQLiteImageSearchQuotaStore
from services.search.image_service import ImageSearchService
from sources.providers.image_search import (
    TraceMoeImageSearchProvider,
    WhatAnimeIsThisImageSearchProvider,
    _parse_results,
)


class ImageSearchPayloadTests(unittest.TestCase):
    def test_trace_payload_with_anilist_info_is_normalized(self) -> None:
        matches = _parse_results(
            "trace_moe",
            "trace.moe",
            {
                "result": [
                    {
                        "anilist": {
                            "id": 130003,
                            "idMal": 47917,
                            "title": {
                                "romaji": "Bocchi the Rock!",
                                "english": "BOCCHI THE ROCK!",
                                "native": "ぼっち・ざ・ろっく！",
                            },
                            "synonyms": ["Bocchi"],
                        },
                        "episode": 1,
                        "from": 123.4,
                        "to": 124.0,
                        "similarity": 0.934,
                        "image": "https://example.invalid/frame.jpg",
                        "video": "https://example.invalid/frame.mp4",
                    }
                ]
            },
        )
        self.assertEqual(len(matches), 1)
        match = matches[0]
        self.assertEqual(match.anilist_id, "130003")
        self.assertEqual(match.mal_id, "47917")
        self.assertEqual(match.episode, "1")
        self.assertAlmostEqual(match.similarity, 0.934)
        self.assertEqual(match.titles["romaji"], "Bocchi the Rock!")

    def test_whatanime_numeric_anilist_payload_uses_same_model(self) -> None:
        matches = _parse_results(
            "whatanimeisthis",
            "What Anime Is This",
            {
                "result": [
                    {
                        "anilist": 104462,
                        "episode": 1,
                        "from": 590.9,
                        "to": 591.2,
                        "similarity": 0.72,
                        "image": "https://example.invalid/result.jpg",
                    }
                ]
            },
        )
        self.assertEqual(matches[0].anilist_id, "104462")
        self.assertEqual(matches[0].titles, {})


class ImageSearchQuotaTests(unittest.TestCase):
    def test_quota_store_is_persistent_and_day_scoped(self) -> None:
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "quota.sqlite3"
            first = SQLiteImageSearchQuotaStore(path)
            first.consume("whatanimeisthis", amount=2, period="2026-10-30")
            first.mark_exhausted("whatanimeisthis", period="2026-10-30")
            second = SQLiteImageSearchQuotaStore(path)
            state = second.state("whatanimeisthis", period="2026-10-30")
            next_day = second.state("whatanimeisthis", period="2026-10-31")
        self.assertEqual(state.used, 2)
        self.assertTrue(state.exhausted)
        self.assertEqual(next_day.used, 0)
        self.assertFalse(next_day.exhausted)

    def test_whatanime_zero_api_limit_disables_local_ceiling(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store = SQLiteImageSearchQuotaStore(Path(temp_dir) / "quota.sqlite3")
            settings = SimpleNamespace(
                whatanimeisthis_api_key="api-key",
                whatanimeisthis_guest_daily_limit=5,
                whatanimeisthis_api_daily_limit=0,
            )
            provider = WhatAnimeIsThisImageSearchProvider(store, settings)
            store.consume("whatanimeisthis", amount=999)
            availability = __import__("asyncio").run(provider.availability())
        self.assertTrue(availability.available)
        self.assertIsNone(availability.remaining)
        self.assertIsNone(availability.limit)

    def test_whatanime_availability_hides_exhausted_local_budget(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store = SQLiteImageSearchQuotaStore(Path(temp_dir) / "quota.sqlite3")
            settings = SimpleNamespace(
                whatanimeisthis_api_key="",
                whatanimeisthis_guest_daily_limit=5,
                whatanimeisthis_api_daily_limit=10,
            )
            provider = WhatAnimeIsThisImageSearchProvider(store, settings)
            for _ in range(5):
                store.consume("whatanimeisthis")
            availability = __import__("asyncio").run(provider.availability())
        self.assertFalse(availability.available)
        self.assertEqual(availability.remaining, 0)
        self.assertEqual(availability.limit, 5)

    def test_trace_api_key_is_optional_header(self) -> None:
        without = TraceMoeImageSearchProvider(SimpleNamespace(trace_moe_api_key=""))
        with_key = TraceMoeImageSearchProvider(
            SimpleNamespace(trace_moe_api_key="secret-key")
        )
        self.assertEqual(without._headers(), {})
        self.assertEqual(with_key._headers(), {"x-trace-key": "secret-key"})


class _FakeImageProvider:
    def __init__(self, key: str, name: str, matches: list[ImageSearchMatch]) -> None:
        self.key = key
        self.name = name
        self.matches = matches

    async def availability(self):
        return ImageSearchAvailability(self.key, self.name, True, 5, 5)

    async def search(self, image):
        return list(self.matches)


class _FakeDirectLookup:
    def __init__(self) -> None:
        self.ids: list[str] = []

    async def lookup(self, external_id, *, source_keys=None, enrich_candidates=True):
        value = str(external_id)
        self.ids.append(value)
        return SearchResultSet(
            items=[
                SearchCandidate(
                    title=f"Resolved {value}",
                    external_ids={"anilist": value, "mal": f"m{value}"},
                    posters=[f"https://example.invalid/{value}.jpg"],
                )
            ]
        )


class ImageSearchProviderHttpTests(unittest.IsolatedAsyncioTestCase):
    async def test_trace_me_uses_key_and_real_server_quota(self) -> None:
        settings = SimpleNamespace(
            trace_moe_api_key="trace-key",
            trace_moe_api_url="https://api.trace.moe",
            trace_moe_request_timeout_seconds=30.0,
            trace_moe_quota_cache_ttl_seconds=30.0,
        )
        provider = TraceMoeImageSearchProvider(settings)
        response = httpx.Response(
            200,
            json={"quota": 200, "quotaUsed": 17},
            request=httpx.Request("GET", "https://api.trace.moe/me"),
        )
        with (
            patch(
                "sources.providers.image_search.http_request",
                AsyncMock(return_value=response),
            ) as request,
            patch(
                "sources.providers.image_search.wait_for_upstream",
                AsyncMock(),
            ),
        ):
            availability = await provider.availability(force=True)
        self.assertTrue(availability.available)
        self.assertEqual(availability.remaining, 183)
        self.assertEqual(availability.limit, 200)
        self.assertEqual(
            request.await_args.kwargs["headers"], {"x-trace-key": "trace-key"}
        )

    async def test_whatanime_daily_quota_response_marks_provider_exhausted(
        self,
    ) -> None:
        with TemporaryDirectory() as temp_dir:
            store = SQLiteImageSearchQuotaStore(Path(temp_dir) / "quota.sqlite3")
            settings = SimpleNamespace(
                whatanimeisthis_api_key="",
                whatanimeisthis_api_url="https://whatanimeisthis.com",
                whatanimeisthis_request_timeout_seconds=30.0,
                whatanimeisthis_guest_daily_limit=5,
                whatanimeisthis_api_daily_limit=10,
            )
            provider = WhatAnimeIsThisImageSearchProvider(store, settings)
            response = httpx.Response(
                429,
                json={"error": "Daily search limit reached"},
                request=httpx.Request(
                    "POST", "https://whatanimeisthis.com/api/anime/search"
                ),
            )
            with (
                patch(
                    "sources.providers.image_search.http_request",
                    AsyncMock(return_value=response),
                ),
                patch(
                    "sources.providers.image_search.wait_for_upstream",
                    AsyncMock(),
                ),
            ):
                with self.assertRaises(Exception) as raised:
                    await provider.search(
                        ImageSearchInput(url="https://example.invalid/frame.png")
                    )
            availability = await provider.availability()
        self.assertIn("Daily search limit", str(raised.exception))
        self.assertFalse(availability.available)

    async def test_whatanime_api_key_search_consumes_local_daily_budget(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store = SQLiteImageSearchQuotaStore(Path(temp_dir) / "quota.sqlite3")
            settings = SimpleNamespace(
                whatanimeisthis_api_key="wait-key",
                whatanimeisthis_api_url="https://whatanimeisthis.com",
                whatanimeisthis_request_timeout_seconds=30.0,
                whatanimeisthis_guest_daily_limit=5,
                whatanimeisthis_api_daily_limit=10,
            )
            provider = WhatAnimeIsThisImageSearchProvider(store, settings)
            response = httpx.Response(
                200,
                json={
                    "result": [
                        {
                            "anilist": 130003,
                            "episode": 1,
                            "from": 1.0,
                            "to": 2.0,
                            "similarity": 0.9,
                        }
                    ]
                },
                request=httpx.Request(
                    "POST", "https://whatanimeisthis.com/api/anime/search"
                ),
            )
            with (
                patch(
                    "sources.providers.image_search.http_request",
                    AsyncMock(return_value=response),
                ) as request,
                patch(
                    "sources.providers.image_search.wait_for_upstream",
                    AsyncMock(),
                ),
            ):
                matches = await provider.search(
                    ImageSearchInput(url="https://example.invalid/frame.png")
                )
            state = store.state("whatanimeisthis")
        self.assertEqual(matches[0].anilist_id, "130003")
        self.assertEqual(state.used, 1)
        self.assertEqual(
            request.await_args.kwargs["headers"],
            {"Authorization": "Bearer wait-key"},
        )
        self.assertEqual(
            request.await_args.kwargs["data"],
            {"url": "https://example.invalid/frame.png"},
        )


class ImageSearchServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_both_sources_same_anilist_id_merge_into_one_candidate(self) -> None:
        left = ImageSearchMatch("trace_moe", "trace.moe", "130003", 0.96, episode="1")
        right = ImageSearchMatch(
            "whatanimeisthis", "What Anime Is This", "130003", 0.91, episode="1"
        )
        lookup = _FakeDirectLookup()
        service = ImageSearchService(
            (
                _FakeImageProvider("trace_moe", "trace.moe", [left]),
                _FakeImageProvider("whatanimeisthis", "What Anime Is This", [right]),
            ),
            lookup,
        )
        result = await service.search(
            ImageSearchInput(url="https://example.invalid/frame.webp"),
            ("trace_moe", "whatanimeisthis"),
        )
        self.assertEqual(len(result.items), 1)
        self.assertEqual(result.items[0].candidate.title, "Resolved 130003")
        self.assertEqual(len(result.items[0].matches), 2)
        self.assertEqual(lookup.ids, ["130003"])

    async def test_different_ids_remain_separate_and_rank_by_similarity(self) -> None:
        service = ImageSearchService(
            (
                _FakeImageProvider(
                    "trace_moe",
                    "trace.moe",
                    [ImageSearchMatch("trace_moe", "trace.moe", "1", 0.70)],
                ),
                _FakeImageProvider(
                    "whatanimeisthis",
                    "What Anime Is This",
                    [
                        ImageSearchMatch(
                            "whatanimeisthis", "What Anime Is This", "2", 0.90
                        )
                    ],
                ),
            ),
            _FakeDirectLookup(),
        )
        result = await service.search(
            ImageSearchInput(content=b"image", content_type="image/png"),
            ("trace_moe", "whatanimeisthis"),
        )
        self.assertEqual(
            [item.candidate.external_ids["anilist"] for item in result.items],
            ["2", "1"],
        )


if __name__ == "__main__":
    unittest.main()
