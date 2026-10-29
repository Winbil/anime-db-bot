from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, patch

import httpx

from core.identity import AnimeIdentity
from core.settings import AppSettings
from sources.providers.skipdb import SkipDBSource


def _response(
    url: str, payload: dict[str, object], status: int = 200
) -> httpx.Response:
    request = httpx.Request("GET", url)
    return httpx.Response(status, json=payload, request=request)


class SkipDBSourceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.settings = AppSettings.from_env({"BOT_TOKEN": "x"}).sources

    def test_supports_confirmed_imdb_or_tmdb_identity(self) -> None:
        source = SkipDBSource(self.settings)
        self.assertTrue(source.supports_identity(AnimeIdentity({"imdb": "tt14115938"})))
        self.assertTrue(source.supports_identity(AnimeIdentity({"tmdb_tv": "119495"})))
        self.assertTrue(source.supports_identity(AnimeIdentity({"tmdb_movie": "123"})))
        self.assertFalse(source.supports_identity(AnimeIdentity({"mal": "48316"})))

    async def test_resolves_confirmed_tmdb_id_through_skipdb_redirect(self) -> None:
        source = SkipDBSource(self.settings)
        response = _response("https://skipdb.tv/title/tt14115938", {})
        with (
            patch("sources.providers.skipdb.wait_for_upstream", new=AsyncMock()),
            patch(
                "sources.providers.skipdb.http_request",
                new=AsyncMock(return_value=response),
            ) as request,
        ):
            imdb = await source.resolve_imdb(AnimeIdentity({"tmdb_tv": "119495"}))
        self.assertEqual(imdb, "tt14115938")
        self.assertIn("/title/tmdb/series/119495", request.await_args.args[2])

    async def test_episode_page_preserves_skipdb_season_and_episode_numbers(
        self,
    ) -> None:
        source = SkipDBSource(self.settings)
        payload = {
            "imdb_id": "tt14115938",
            "name": "The Eminence in Shadow",
            "media_type": "series",
            "episodes": [
                {
                    "season": 1,
                    "episode": 1,
                    "name": "One",
                    "runtimeMs": 1_440_000,
                    "coverage": {"intro": {"approved": 1, "pending": 0}},
                    "hasIntroAbsence": False,
                },
                {
                    "season": 2,
                    "episode": 1,
                    "name": "Two",
                    "runtimeMs": 1_440_000,
                    "coverage": {"outro": {"approved": 1, "pending": 0}},
                    "hasIntroAbsence": False,
                },
            ],
        }
        with (
            patch("sources.providers.skipdb.wait_for_upstream", new=AsyncMock()),
            patch(
                "sources.providers.skipdb.http_request",
                new=AsyncMock(
                    return_value=_response(
                        "https://skipdb.tv/api/titles/tt14115938", payload
                    )
                ),
            ),
        ):
            page = await source.load_episode_page(
                AnimeIdentity({"imdb": "tt14115938"}), page=1
            )
        self.assertEqual([item.number for item in page.items], [10001, 20001])
        self.assertEqual(
            [(item.season_number, item.episode_number) for item in page.items],
            [(1, 1), (2, 1)],
        )
        self.assertEqual(page.items[0].skip_types, ("intro",))
        self.assertEqual(page.items[1].skip_types, ("outro",))

    async def test_episode_detail_loads_segments_without_reloading_cached_title(
        self,
    ) -> None:
        source = SkipDBSource(self.settings)
        title = {
            "imdb_id": "tt14115938",
            "name": "The Eminence in Shadow",
            "media_type": "series",
            "episodes": [
                {
                    "season": 1,
                    "episode": 1,
                    "name": "One",
                    "runtimeMs": 1_440_000,
                    "coverage": {},
                    "hasIntroAbsence": False,
                }
            ],
        }
        segments = {
            "segments": {
                "intro": {
                    "start_ms": 61_000,
                    "end_ms": 91_000,
                    "match": "exact",
                    "adjusted": False,
                    "offset_ms": 0,
                    "confidence": 0.93,
                },
                "recap": None,
                "outro": {
                    "start_ms": 1_380_000,
                    "end_ms": 1_440_000,
                    "match": "exact",
                    "adjusted": False,
                    "offset_ms": 0,
                    "confidence": 0.88,
                },
                "preview": None,
            }
        }
        request = AsyncMock(
            side_effect=[
                _response("https://skipdb.tv/api/titles/tt14115938", title),
                _response("https://skipdb.tv/api/segments", segments),
            ]
        )
        identity = AnimeIdentity({"imdb": "tt14115938"})
        with (
            patch("sources.providers.skipdb.wait_for_upstream", new=AsyncMock()),
            patch("sources.providers.skipdb.http_request", new=request),
        ):
            await source.load_episode_page(identity, page=1)
            episode = await source.load_episode(identity, 10001)
        self.assertIsNotNone(episode)
        assert episode is not None
        self.assertEqual(set(episode.skip_segments), {"intro", "outro"})
        self.assertEqual(episode.skip_segments["intro"].start_ms, 61_000)
        self.assertEqual(episode.skip_segments["intro"].confidence, 0.93)
        self.assertEqual(request.await_count, 2)
        params = request.await_args_list[-1].kwargs["params"]
        self.assertEqual(params["season"], 1)
        self.assertEqual(params["episode"], 1)
        self.assertEqual(params["duration"], 1440)


if __name__ == "__main__":
    unittest.main()
