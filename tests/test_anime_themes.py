from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, patch

import httpx

from core.anime_themes import AnimeThemeEntry
from core.identity import AnimeIdentity
from services.media.anime_themes import AnimeThemeService
from sources.providers.animethemes import AnimeThemesSource


def _response(payload: dict[str, object]) -> httpx.Response:
    return httpx.Response(
        200,
        json=payload,
        request=httpx.Request("GET", "https://api.animethemes.test/anime/"),
    )


def _theme(
    *,
    theme_id: int,
    slug: str,
    kind: str,
    sequence: int | None,
    title: str,
    artist: str,
    entries: list[dict[str, object]],
) -> dict[str, object]:
    return {
        "id": theme_id,
        "slug": slug,
        "type": kind,
        "sequence": sequence,
        "song": {
            "id": theme_id + 100,
            "title": title,
            "artists": [{"id": theme_id + 200, "name": artist}],
        },
        "animethemeentries": entries,
    }


def _entry(
    entry_id: int,
    episodes: str | None,
    *,
    version: int = 1,
    spoiler: bool = False,
    nsfw: bool = False,
    link: str | None = None,
) -> dict[str, object]:
    videos: list[dict[str, object]] = []
    if link:
        videos = [
            {
                "id": entry_id + 1000,
                "link": link,
                "nc": False,
                "resolution": 720,
                "subbed": False,
                "source": "WEB",
            },
            {
                "id": entry_id + 2000,
                "link": link.replace(".webm", "-NCBD1080.webm"),
                "nc": True,
                "resolution": 1080,
                "subbed": False,
                "source": "BD",
            },
        ]
    return {
        "id": entry_id,
        "episodes": episodes,
        "version": version,
        "spoiler": spoiler,
        "nsfw": nsfw,
        "videos": videos,
    }


class AnimeThemesSourceTests(unittest.IsolatedAsyncioTestCase):
    def test_requires_confirmed_anilist_or_mal_id(self) -> None:
        source = AnimeThemesSource(api_url="https://api.animethemes.test")
        self.assertTrue(source.supports_identity(AnimeIdentity({"anilist": "154587"})))
        self.assertTrue(source.supports_identity(AnimeIdentity({"mal": "52991"})))
        self.assertFalse(source.supports_identity(AnimeIdentity({"anidb": "18114"})))
        self.assertFalse(source.supports_identity(AnimeIdentity({"anilist": "bad"})))

    async def test_parses_themes_entries_artists_and_best_video(self) -> None:
        payload = {
            "anime": [
                {
                    "id": 4136,
                    "name": "Sousou no Frieren",
                    "slug": "sousou_no_frieren",
                    "animethemes": [
                        _theme(
                            theme_id=12476,
                            slug="OP1",
                            kind="OP",
                            sequence=1,
                            title="Yuusha",
                            artist="YOASOBI",
                            entries=[
                                _entry(
                                    14598,
                                    "1-16",
                                    link="https://v.animethemes.test/Frieren-OP1.webm",
                                )
                            ],
                        ),
                        _theme(
                            theme_id=12477,
                            slug="ED1",
                            kind="ED",
                            sequence=1,
                            title="Anytime Anywhere",
                            artist="milet",
                            entries=[
                                _entry(14599, "1-14, 16"),
                                _entry(14823, "17-27", version=2),
                                _entry(14965, "28", version=3, spoiler=True),
                                _entry(19999, "29", nsfw=True),
                            ],
                        ),
                    ],
                }
            ]
        }
        request = AsyncMock(return_value=_response(payload))
        source = AnimeThemesSource(
            api_url="https://api.animethemes.test",
            cache_ttl_seconds=0,
        )
        with (
            patch("sources.providers.animethemes.wait_for_upstream", new=AsyncMock()),
            patch("sources.providers.animethemes.http_request", new=request),
        ):
            values = await source.load_themes(AnimeIdentity({"anilist": "154587"}))

        self.assertEqual(len(values), 4)
        opening = values[0]
        self.assertEqual(opening.label, "OP1")
        self.assertEqual(opening.title, "Yuusha")
        self.assertEqual(opening.artists, ("YOASOBI",))
        self.assertEqual(opening.episode_ranges, ((1, 16),))
        self.assertEqual(
            opening.video_url,
            "https://v.animethemes.test/Frieren-OP1-NCBD1080.webm",
        )
        self.assertTrue(any(item.spoiler and item.version == 3 for item in values))
        self.assertFalse(any(item.episodes == "29" for item in values))
        params = request.await_args.kwargs["params"]
        self.assertEqual(params["filter[site]"], "AniList")
        self.assertEqual(params["filter[external_id]"], "154587")
        self.assertIn("animethemes.song.artists", params["include"])

    async def test_anilist_miss_falls_back_to_confirmed_mal_without_title_search(
        self,
    ) -> None:
        request = AsyncMock(
            side_effect=[
                _response({"anime": []}),
                _response(
                    {
                        "anime": [
                            {
                                "id": 1,
                                "animethemes": [
                                    _theme(
                                        theme_id=2,
                                        slug="OP1",
                                        kind="OP",
                                        sequence=1,
                                        title="Song",
                                        artist="Artist",
                                        entries=[_entry(3, "1-12")],
                                    )
                                ],
                            }
                        ]
                    }
                ),
            ]
        )
        source = AnimeThemesSource(
            api_url="https://api.animethemes.test",
            cache_ttl_seconds=0,
        )
        with (
            patch("sources.providers.animethemes.wait_for_upstream", new=AsyncMock()),
            patch("sources.providers.animethemes.http_request", new=request),
        ):
            values = await source.load_themes(
                AnimeIdentity({"anilist": "100", "mal": "200"})
            )

        self.assertEqual([item.label for item in values], ["OP1"])
        self.assertEqual(request.await_count, 2)
        self.assertEqual(
            request.await_args_list[0].kwargs["params"]["filter[site]"], "AniList"
        )
        self.assertEqual(
            request.await_args_list[1].kwargs["params"]["filter[site]"],
            "MyAnimeList",
        )


class AnimeThemeServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_episode_scope_selects_versions_without_guessing(self) -> None:
        class _Source:
            name = "AnimeThemes"
            display_name = "AnimeThemes"

            @staticmethod
            def supports_identity(identity: AnimeIdentity) -> bool:
                return identity.has("anilist")

            async def load_themes(
                self, identity: AnimeIdentity
            ) -> list[AnimeThemeEntry]:
                return [
                    AnimeThemeEntry(
                        "opening",
                        "OP1",
                        "Yuusha",
                        ("YOASOBI",),
                        1,
                        "1-16",
                        ((1, 16),),
                        1,
                    ),
                    AnimeThemeEntry(
                        "opening",
                        "OP2",
                        "Haru",
                        ("Yorushika",),
                        2,
                        "17-28",
                        ((17, 28),),
                        1,
                    ),
                    AnimeThemeEntry(
                        "ending",
                        "ED1",
                        "Anytime Anywhere",
                        ("milet",),
                        1,
                        "1-14, 16",
                        ((1, 14), (16, 16)),
                        1,
                    ),
                    AnimeThemeEntry(
                        "ending",
                        "ED1",
                        "Anytime Anywhere",
                        ("milet",),
                        1,
                        "17-27",
                        ((17, 27),),
                        2,
                    ),
                    AnimeThemeEntry(
                        "ending",
                        "ED1-TV",
                        "bliss",
                        ("milet",),
                        None,
                        "1",
                        ((1, 1),),
                        1,
                    ),
                ]

        service = AnimeThemeService(_Source())
        episode_1 = await service.load_episode_themes(
            AnimeIdentity({"anilist": "1"}), 1
        )
        episode_17 = await service.load_episode_themes(
            AnimeIdentity({"anilist": "1"}), 17
        )

        self.assertEqual([item.label for item in episode_1], ["OP1", "ED1", "ED1-TV"])
        self.assertEqual([item.label for item in episode_17], ["OP2", "ED1"])
        self.assertEqual(episode_17[1].version, 2)

    async def test_unscoped_theme_is_used_only_when_unambiguous(self) -> None:
        class _Source:
            name = "AnimeThemes"
            display_name = "AnimeThemes"

            @staticmethod
            def supports_identity(identity: AnimeIdentity) -> bool:
                return True

            def __init__(self, values: list[AnimeThemeEntry]) -> None:
                self.values = values

            async def load_themes(
                self, identity: AnimeIdentity
            ) -> list[AnimeThemeEntry]:
                return self.values

        one = AnimeThemeService(
            _Source([AnimeThemeEntry("opening", "OP1", title="One")])
        )
        many = AnimeThemeService(
            _Source(
                [
                    AnimeThemeEntry("opening", "OP1", title="One"),
                    AnimeThemeEntry("opening", "OP2", title="Two"),
                ]
            )
        )
        self.assertEqual(
            [
                item.label
                for item in await one.load_episode_themes(
                    AnimeIdentity({"mal": "1"}), 5
                )
            ],
            ["OP1"],
        )
        self.assertEqual(
            await many.load_episode_themes(AnimeIdentity({"mal": "1"}), 5),
            [],
        )


if __name__ == "__main__":
    unittest.main()
