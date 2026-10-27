from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, patch

from core.identity import AnimeIdentity
from sources.jikan import JikanSource


class JikanSourceTests(unittest.IsolatedAsyncioTestCase):
    async def test_jikan_uses_existing_mal_identity_without_new_identity_key(self) -> None:
        source = JikanSource()
        payload = {
            "page": 1,
            "last_visible_page": 2,
            "has_next_page": True,
            "data": [
                {
                    "number": 1,
                    "title": "First Episode",
                    "title_japanese": "第一話",
                    "title_romaji": "Dai Ichi-wa",
                    "aired_at": "2026-01-01T00:00:00+00:00",
                    "score": 4.7,
                    "filler": False,
                    "recap": False,
                    "url": "https://myanimelist.net/anime/123/_/episode/1",
                }
            ],
        }

        with patch("sources.jikan._get", new=AsyncMock(return_value=payload)) as getter:
            page = await source.load_episode_page(AnimeIdentity({"mal": "123"}), page=1)

        getter.assert_awaited_once_with("/anime/123/episodes", params={"page": 1})
        self.assertEqual(source.source_key, "mal")
        self.assertEqual(source.backend_key, "jikan")
        self.assertEqual(page.items[0].source, "mal")
        self.assertEqual(page.items[0].backend, "jikan")
        self.assertEqual(page.items[0].number, 1)
        self.assertTrue(page.has_next)

    async def test_episode_detail_maps_jikan_only_fields(self) -> None:
        source = JikanSource()
        payload = {
            "data": {
                "number": 7,
                "title": "Episode Seven",
                "aired_at": "2026-02-02T00:00:00+00:00",
                "duration_seconds": 1440,
                "filler": True,
                "recap": False,
                "synopsis": "Episode synopsis.",
                "url": "https://myanimelist.net/anime/123/_/episode/7",
            }
        }

        with patch("sources.jikan._get", new=AsyncMock(return_value=payload)):
            episode = await source.load_episode(AnimeIdentity({"mal": "123"}), 7)

        self.assertIsNotNone(episode)
        assert episode is not None
        self.assertEqual(episode.duration_seconds, 1440)
        self.assertEqual(episode.synopsis, "Episode synopsis.")
        self.assertTrue(episode.filler)

    async def test_missing_mal_identity_does_not_call_service(self) -> None:
        source = JikanSource()
        with patch("sources.jikan._get", new=AsyncMock()) as getter:
            page = await source.load_episode_page(AnimeIdentity({"anilist": "10"}))
        getter.assert_not_awaited()
        self.assertEqual(page.items, [])


if __name__ == "__main__":
    unittest.main()
