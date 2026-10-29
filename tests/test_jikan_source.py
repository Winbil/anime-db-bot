from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, patch

from core.identity import AnimeIdentity
from sources.providers.jikan import JikanSource


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

        with patch("sources.providers.jikan._get", new=AsyncMock(return_value=payload)) as getter:
            page = await source.load_episode_page(AnimeIdentity({"mal": "123"}), page=1)

        args, kwargs = getter.await_args
        self.assertEqual(args, ("/anime/123/episodes",))
        self.assertEqual(kwargs["params"], {"page": 1})
        self.assertIs(kwargs["settings"], source._settings)
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

        with patch("sources.providers.jikan._get", new=AsyncMock(return_value=payload)):
            episode = await source.load_episode(AnimeIdentity({"mal": "123"}), 7)

        self.assertIsNotNone(episode)
        assert episode is not None
        self.assertEqual(episode.duration_seconds, 1440)
        self.assertEqual(episode.synopsis, "Episode synopsis.")
        self.assertTrue(episode.filler)

    async def test_missing_mal_identity_does_not_call_service(self) -> None:
        source = JikanSource()
        with patch("sources.providers.jikan._get", new=AsyncMock()) as getter:
            page = await source.load_episode_page(AnimeIdentity({"anilist": "10"}))
        getter.assert_not_awaited()
        self.assertEqual(page.items, [])

    async def test_trailers_keep_mal_jikan_provenance(self) -> None:
        source = JikanSource()
        payload = {
            "data": [
                {
                    "title": "PV 1",
                    "youtube_id": "abc123",
                    "url": "https://www.youtube.com/watch?v=abc123",
                    "embed_url": "https://www.youtube.com/embed/abc123",
                    "thumbnail": "https://img.youtube.com/vi/abc123/maxresdefault.jpg",
                }
            ]
        }
        with patch("sources.providers.jikan._get", new=AsyncMock(return_value=payload)) as getter:
            trailers = await source.load_trailers(AnimeIdentity({"mal": "123"}))

        args, kwargs = getter.await_args
        self.assertEqual(args, ("/anime/123/trailers",))
        self.assertEqual(kwargs["operation"], "trailers")
        self.assertIs(kwargs["settings"], source._settings)
        self.assertEqual(len(trailers), 1)
        self.assertEqual(trailers[0].source, "mal")
        self.assertEqual(trailers[0].backend, "jikan")
        self.assertEqual(trailers[0].title, "PV 1")
        self.assertEqual(trailers[0].hosting, "YouTube")

    async def test_metadata_supplement_maps_existing_mal_fields(self) -> None:
        source = JikanSource()
        payload = {
            "data": {
                "licensors": ["Sentai Filmworks", "Sentai Filmworks", "Muse"],
                "score_distribution": {"10": 120, "9": 80, "0": 999},
            }
        }
        with patch("sources.providers.jikan._get", new=AsyncMock(return_value=payload)) as getter:
            result = await source.load_metadata_supplement(AnimeIdentity({"mal": "123"}))

        args, kwargs = getter.await_args
        self.assertEqual(args, ("/anime/123/supplement",))
        self.assertEqual(kwargs["operation"], "metadata")
        self.assertIs(kwargs["settings"], source._settings)
        self.assertEqual(result["licensors"], ["Sentai Filmworks", "Muse"])
        self.assertEqual(result["score_distribution"], {10: 120, 9: 80})

    async def test_people_payload_maps_staff_and_japanese_voice_roles(self) -> None:
        source = JikanSource()
        payload = {
            "data": {
                "staff": [{"person": {"mal_id": 1, "name": "Director Person", "image_url": "https://example.invalid/director.jpg"}, "roles": ["Director"]}],
                "voices": [
                    {"person": {"mal_id": 2, "name": "Voice Person", "image_url": "https://example.invalid/voice.jpg"}, "character": "Hero"},
                    {"person": {"mal_id": 2, "name": "Voice Person", "image_url": "https://example.invalid/voice.jpg"}, "character": "Other Hero"},
                ],
            }
        }
        with patch("sources.providers.jikan._get", new=AsyncMock(return_value=payload)) as getter:
            staff = await source.load_staff(AnimeIdentity({"mal": "123"}))
            voices = await source.load_voices(AnimeIdentity({"mal": "123"}))

        self.assertEqual(getter.await_count, 1, "staff/voices should share the people cache")
        self.assertEqual(staff[0].roles, ["director"])
        self.assertEqual(staff[0].external_ids, {"mal": "1"})
        self.assertEqual(len(voices), 1)
        self.assertEqual(voices[0].roles, ["voice_of::Hero", "voice_of::Other Hero"])
        self.assertIn("MAL (MyAnimeList) / Jikan", voices[0].portraits)


if __name__ == "__main__":
    unittest.main()
