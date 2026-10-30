from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, Mock, patch

from core.identity import AnimeIdentity
from core.settings import AppSettings
from core.source_keys import SourceKey
from search.providers.kitsu import KitsuSearchProvider
from sources.providers import kitsu
from sources.providers.kitsu import KitsuSource


def _mapping(mapping_id: str, site: str, external_id: str) -> dict:
    return {
        "id": mapping_id,
        "type": "mappings",
        "attributes": {"externalSite": site, "externalId": external_id},
    }


def _detail_payload() -> dict:
    return {
        "data": {
            "id": "44196",
            "type": "anime",
            "attributes": {
                "slug": "bocchi-the-rock",
                "titles": {
                    "en": "BOCCHI THE ROCK!",
                    "en_jp": "Bocchi the Rock!",
                    "ja_jp": "ぼっち・ざ・ろっく！",
                },
                "canonicalTitle": "Bocchi the Rock!",
                "abbreviatedTitles": ["BTR"],
                "synopsis": "A shy guitarist joins a band.",
                "averageRating": "83.49",
                "ratingFrequencies": {"18": "20", "20": "30"},
                "userCount": 15106,
                "favoritesCount": 357,
                "startDate": "2022-10-09",
                "endDate": "2022-12-25",
                "nextRelease": None,
                "popularityRank": 1143,
                "ratingRank": 79,
                "ageRating": "PG",
                "subtype": "TV",
                "status": "finished",
                "posterImage": {"original": "https://media.example/poster.jpg"},
                "episodeCount": 12,
                "episodeLength": 24,
                "youtubeVideoId": "SyMMZF5zNW4",
            },
            "relationships": {
                "mappings": {
                    "data": [
                        {"type": "mappings", "id": "m1"},
                        {"type": "mappings", "id": "m2"},
                        {"type": "mappings", "id": "m3"},
                    ]
                },
                "categories": {"data": [{"type": "categories", "id": "c1"}]},
                "productions": {"data": [{"type": "mediaProductions", "id": "p1"}]},
            },
        },
        "included": [
            _mapping("m1", "myanimelist/anime", "47917"),
            _mapping("m2", "anilist/anime", "130003"),
            _mapping("m3", "anidb", "16063"),
            {
                "id": "c1",
                "type": "categories",
                "attributes": {"title": "Comedy"},
            },
            {
                "id": "p1",
                "type": "mediaProductions",
                "attributes": {"role": "studio"},
                "relationships": {
                    "company": {"data": {"type": "producers", "id": "s1"}}
                },
            },
            {
                "id": "s1",
                "type": "producers",
                "attributes": {"name": "CLOVERWORKS"},
            },
        ],
    }


def _episode_payload(number: int = 3) -> dict:
    return {
        "data": [
            {
                "id": "e3",
                "type": "episodes",
                "attributes": {
                    "titles": {"en": "Be Right There"},
                    "canonicalTitle": "Be Right There",
                    "seasonNumber": 1,
                    "number": number,
                    "airdate": "2022-10-23",
                    "length": 24,
                    "synopsis": "Bocchi looks for a vocalist.",
                },
            }
        ],
        "meta": {"count": 12},
        "links": {"next": "https://example.invalid/next"},
    }


class KitsuSourceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.settings = AppSettings.from_env(
            {
                "KITSU_API_URL": "https://kitsu.example/api/edge",
                "KITSU_CACHE_TTL_SECONDS": "60",
            }
        ).sources
        self.source = KitsuSource(self.settings)
        kitsu._DETAIL_CACHE.clear()

    async def test_details_use_native_id_and_confirmed_peer_mappings(self) -> None:
        response = Mock()
        response.json.return_value = _detail_payload()
        request = AsyncMock(return_value=response)
        with patch("sources.providers.kitsu.http_request", request):
            record = await self.source.get_details(AnimeIdentity({"kitsu": "44196"}))

        self.assertIsNotNone(record)
        assert record is not None
        self.assertEqual(record.source, "Kitsu")
        self.assertEqual(record.source_id, "44196")
        self.assertEqual(record.external_ids["kitsu"], "44196")
        self.assertEqual(record.external_ids["mal"], "47917")
        self.assertEqual(record.external_ids["anilist"], "130003")
        self.assertEqual(record.external_ids["anidb"], "16063")
        self.assertEqual(record.titles["romaji"], "Bocchi the Rock!")
        self.assertEqual(record.kind, "tv")
        self.assertEqual(record.status, "finished")
        self.assertEqual(record.rating, "pg")
        self.assertEqual(record.episodes_total, 12)
        self.assertEqual(record.episodes_aired, 12)
        self.assertEqual(record.score, 8.35)
        self.assertIn("comedy", [value.casefold() for value in record.genres])
        self.assertEqual(record.studios, ["CLOVERWORKS"])
        self.assertEqual(
            record.urls["Kitsu"], "https://kitsu.app/anime/bocchi-the-rock"
        )

    async def test_cached_detail_serves_metadata_popularity_and_description(
        self,
    ) -> None:
        response = Mock()
        response.json.return_value = _detail_payload()
        request = AsyncMock(return_value=response)
        identity = AnimeIdentity({"kitsu": "44196"})
        with patch("sources.providers.kitsu.http_request", request):
            record = await self.source.get_details(identity)
            popularity = await self.source.load_popularity(identity)
            description = await self.source.load_description(identity)

        self.assertIsNotNone(record)
        self.assertEqual(popularity.rank, 79)
        self.assertEqual(popularity.popularity_rank, 1143)
        self.assertEqual(popularity.list_users, 15106)
        self.assertEqual(popularity.scoring_users, 50)
        self.assertEqual(popularity.favorites, 357)
        self.assertEqual(description.description, "A shy guitarist joins a band.")
        request.assert_awaited_once()

    async def test_trailer_uses_kitsu_youtube_id_and_thumbnail(self) -> None:
        response = Mock()
        response.json.return_value = _detail_payload()
        request = AsyncMock(return_value=response)
        with (
            patch("sources.providers.kitsu.http_request", request),
            patch("sources.providers.kitsu.wait_for_upstream", AsyncMock()),
        ):
            items = await self.source.load_trailers(AnimeIdentity({"kitsu": "44196"}))

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].backend, "kitsu")
        self.assertEqual(items[0].hosting, "YouTube")
        self.assertIn("SyMMZF5zNW4", items[0].url)
        self.assertIn("SyMMZF5zNW4", items[0].thumbnail or "")

    async def test_episode_page_and_direct_episode(self) -> None:
        page_response = Mock()
        page_response.json.return_value = _episode_payload(3)
        direct_response = Mock()
        direct_response.json.return_value = _episode_payload(3)
        request = AsyncMock(side_effect=[page_response, direct_response])
        with (
            patch("sources.providers.kitsu.http_request", request),
            patch("sources.providers.kitsu.wait_for_upstream", AsyncMock()),
        ):
            page = await self.source.load_episode_page(
                AnimeIdentity({"kitsu": "44196"}), page=1
            )
            episode = await self.source.load_episode(
                AnimeIdentity({"kitsu": "44196"}), 3
            )

        self.assertEqual(page.last_visible_page, 1)
        self.assertFalse(page.has_next)
        self.assertEqual(page.items[0].number, 3)
        self.assertEqual(page.items[0].duration_seconds, 1440)
        self.assertIsNotNone(episode)
        assert episode is not None
        self.assertEqual(episode.titles["english"], "Be Right There")
        self.assertEqual(episode.source, "kitsu")

    async def test_episode_backend_combines_api_chunks_into_100_item_logical_page(
        self,
    ) -> None:
        def item(number: int) -> dict:
            payload = _episode_payload(number)
            return payload["data"][0]

        first = Mock()
        first.json.return_value = {
            "data": [item(number) for number in range(101, 121)],
            "meta": {"count": 125},
            "links": {"next": "https://example.invalid/next"},
        }
        second = Mock()
        second.json.return_value = {
            "data": [item(number) for number in range(121, 126)],
            "meta": {"count": 125},
            "links": {},
        }
        request = AsyncMock(side_effect=[first, second])
        with (
            patch("sources.providers.kitsu.http_request", request),
            patch("sources.providers.kitsu.wait_for_upstream", AsyncMock()),
        ):
            page = await self.source.load_episode_page(
                AnimeIdentity({"kitsu": "44196"}), page=2
            )

        self.assertEqual(
            [episode.number for episode in page.items], list(range(101, 126))
        )
        self.assertEqual(page.page, 2)
        self.assertEqual(page.last_visible_page, 2)
        self.assertFalse(page.has_next)
        self.assertEqual(request.await_count, 2)
        offsets = [
            call.kwargs["params"]["page[offset]"] for call in request.await_args_list
        ]
        self.assertEqual(offsets, [100, 120])

    async def test_missing_kitsu_identity_does_not_call_network(self) -> None:
        request = AsyncMock()
        with patch("sources.providers.kitsu.http_request", request):
            record = await self.source.get_details(AnimeIdentity({"mal": "47917"}))
        self.assertIsNone(record)
        request.assert_not_awaited()

    def test_source_identity_is_native_kitsu(self) -> None:
        self.assertEqual(self.source.source_key, SourceKey.KITSU)
        self.assertEqual(self.source.backend_key, "kitsu")


class KitsuSearchTests(unittest.IsolatedAsyncioTestCase):
    async def test_search_returns_peer_ids_and_score(self) -> None:
        payload = _detail_payload()
        item = payload["data"]
        body = {
            "data": [item],
            "included": payload["included"][:3],
            "links": {"next": "https://example.invalid/next"},
        }
        response = Mock()
        response.json.return_value = body
        request = AsyncMock(return_value=response)
        settings = AppSettings.from_env(
            {"KITSU_API_URL": "https://kitsu.example/api/edge"}
        ).sources
        provider = KitsuSearchProvider(settings)
        with (
            patch("search.providers.kitsu.http_request", request),
            patch("search.providers.kitsu.wait_for_upstream", AsyncMock()),
        ):
            page = await provider.search("Bocchi the Rock", page=1, limit=50)

        self.assertEqual(page.page_size, 20)
        self.assertTrue(page.has_next)
        self.assertEqual(len(page.items), 1)
        item = page.items[0]
        self.assertEqual(item.title, "BOCCHI THE ROCK!")
        self.assertEqual(item.romaji_title, "Bocchi the Rock!")
        self.assertEqual(item.year, 2022)
        self.assertEqual(item.external_ids["kitsu"], "44196")
        self.assertEqual(item.external_ids["mal"], "47917")
        self.assertEqual(item.external_ids["anilist"], "130003")
        self.assertEqual(item.scores["Kitsu"], 8.35)
        self.assertEqual(item.posters, ["https://media.example/poster.jpg"])


if __name__ == "__main__":
    unittest.main()
