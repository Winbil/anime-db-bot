from __future__ import annotations

import sqlite3
from tempfile import TemporaryDirectory
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx

from core.episode_segments import EpisodeSegment
from core.identity import AnimeIdentity
from services.media.episode_segments import EpisodeSegmentService, aggregate_segments
from sources.providers.anime_skip import AnimeSkipSegmentSource
from sources.providers.aniskip import AniSkipSegmentSource
from sources.providers.baha_anime_skip import BahaAnimeSkipSegmentSource


def _response(payload: dict[str, object], status: int = 200) -> httpx.Response:
    request = httpx.Request("GET", "https://api.aniskip.test/v2/skip-times/1/2")
    return httpx.Response(status, json=payload, request=request)


class _SegmentSource:
    def __init__(self, backend: str, *, supported_key: str = "mal") -> None:
        self.backend_key = backend
        self.display_name = backend.upper()
        self.name = self.display_name
        self.supported_key = supported_key

    def supports_identity(self, identity: AnimeIdentity) -> bool:
        return identity.has(self.supported_key)

    async def load_segments(
        self,
        identity: AnimeIdentity,
        episode_number: int,
        *,
        episode_length_seconds: int | None = None,
    ) -> list[EpisodeSegment]:
        return [
            EpisodeSegment(
                kind="opening",
                source=self.backend_key,
                start_seconds=90.0,
                end_seconds=180.0,
            )
        ]


class EpisodeSegmentServiceTests(unittest.IsolatedAsyncioTestCase):
    def test_consensus_uses_compatible_cluster_not_global_average(self) -> None:
        result = aggregate_segments(
            {
                "a": [EpisodeSegment("opening", "a", 90.0, 180.0)],
                "b": [EpisodeSegment("opening", "b", 91.0, 181.0)],
                "bad": [EpisodeSegment("opening", "bad", 300.0, 390.0)],
            }
        )
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].start_seconds, 90.5)
        self.assertEqual(result[0].end_seconds, 180.5)
        self.assertEqual(result[0].sources, ("a", "b"))

    async def test_service_is_independent_from_episode_metadata_backend(self) -> None:
        service = EpisodeSegmentService([_SegmentSource("aniskip")])
        identity = AnimeIdentity({"mal": "1", "anidb": "2"})
        self.assertEqual(service.available_backends(identity), ["aniskip"])
        values = await service.load_segments(identity, 7, backend="aniskip")
        self.assertEqual(values[0].source, "aniskip")


class AniSkipSegmentSourceTests(unittest.IsolatedAsyncioTestCase):
    def test_requires_confirmed_positive_mal_id(self) -> None:
        source = AniSkipSegmentSource(api_url="https://api.aniskip.test/v2")
        self.assertTrue(source.supports_identity(AnimeIdentity({"mal": "5114"})))
        self.assertFalse(source.supports_identity(AnimeIdentity({"anidb": "1"})))
        self.assertFalse(source.supports_identity(AnimeIdentity({"mal": "bad"})))

    async def test_parses_all_supported_aniskip_segment_shapes(self) -> None:
        source = AniSkipSegmentSource(
            api_url="https://api.aniskip.test/v2",
            cache_ttl_seconds=0,
        )
        payload = {
            "found": True,
            "results": [
                {
                    "interval": {"startTime": 90.5, "endTime": 180.25},
                    "skipType": "op",
                    "skipId": "op-id",
                    "episodeLength": 1420,
                },
                {
                    "interval": {"startTime": 1330.0, "endTime": 1420.0},
                    "skipType": "ed",
                    "skipId": "ed-id",
                    "episodeLength": 1420,
                },
                {
                    "interval": {"startTime": 0.0, "endTime": 45.0},
                    "skipType": "recap",
                    "skipId": "recap-id",
                    "episodeLength": 1420,
                },
            ],
        }
        request = AsyncMock(return_value=_response(payload))
        with (
            patch("sources.providers.aniskip.wait_for_upstream", new=AsyncMock()),
            patch("sources.providers.aniskip.http_request", new=request),
        ):
            values = await source.load_segments(
                AnimeIdentity({"mal": "1"}),
                2,
                episode_length_seconds=1420,
            )
        self.assertEqual([item.kind for item in values], ["recap", "opening", "ending"])
        opening = next(item for item in values if item.kind == "opening")
        self.assertEqual(opening.start_seconds, 90.5)
        self.assertEqual(opening.end_seconds, 180.25)
        self.assertEqual(opening.source_segment_id, "op-id")
        self.assertEqual(opening.raw_kind, "op")
        self.assertEqual(opening.episode_length_seconds, 1420.0)
        params = request.await_args.kwargs["params"]
        self.assertIn(("episodeLength", 1420), params)
        self.assertIn(("types", "mixed-op"), params)
        self.assertIn(("types", "mixed-ed"), params)

    async def test_missing_mal_identity_never_calls_network(self) -> None:
        source = AniSkipSegmentSource(api_url="https://api.aniskip.test/v2")
        request = AsyncMock()
        with patch("sources.providers.aniskip.http_request", new=request):
            values = await source.load_segments(AnimeIdentity({"anidb": "1"}), 1)
        self.assertEqual(values, [])
        request.assert_not_awaited()


class AnimeSkipSegmentSourceTests(unittest.IsolatedAsyncioTestCase):
    def test_requires_client_id_and_confirmed_anilist_id(self) -> None:
        enabled = AnimeSkipSegmentSource(
            client_id="client-id",
            api_url="https://anime-skip.test/api",
        )
        disabled = AnimeSkipSegmentSource(
            client_id="",
            api_url="https://anime-skip.test/api",
        )
        self.assertTrue(enabled.supports_identity(AnimeIdentity({"anilist": "16498"})))
        self.assertFalse(enabled.supports_identity(AnimeIdentity({"mal": "16498"})))
        self.assertFalse(enabled.supports_identity(AnimeIdentity({"anilist": "bad"})))
        self.assertFalse(
            disabled.supports_identity(AnimeIdentity({"anilist": "16498"}))
        )

    async def test_parses_graphql_boundaries_into_segments_and_sends_client_id(
        self,
    ) -> None:
        source = AnimeSkipSegmentSource(
            client_id="client-id",
            api_url="https://anime-skip.test/api",
            cache_ttl_seconds=0,
        )
        payload = {
            "data": {
                "findShowsByExternalId": [
                    {
                        "id": "show-id",
                        "episodes": [
                            {
                                "id": "bad-duplicate",
                                "number": "2",
                                "absoluteNumber": None,
                                "baseDuration": 1420,
                                "timestamps": [
                                    {
                                        "id": "bad",
                                        "at": -100,
                                        "source": "ANIME_SKIP",
                                        "type": {"name": "Intro"},
                                    }
                                ],
                            },
                            {
                                "id": "episode-id",
                                "number": "2",
                                "absoluteNumber": None,
                                "baseDuration": 1420,
                                "timestamps": [
                                    {
                                        "id": "canon-0",
                                        "at": 0,
                                        "source": "ANIME_SKIP",
                                        "type": {"name": "Canon"},
                                    },
                                    {
                                        "id": "intro",
                                        "at": 90,
                                        "source": "ANIME_SKIP",
                                        "type": {"name": "Intro"},
                                    },
                                    {
                                        "id": "canon-1",
                                        "at": 180,
                                        "source": "ANIME_SKIP",
                                        "type": {"name": "Canon"},
                                    },
                                    {
                                        "id": "credits",
                                        "at": 1300,
                                        "source": "ANIME_SKIP",
                                        "type": {"name": "Credits"},
                                    },
                                    {
                                        "id": "preview",
                                        "at": 1390,
                                        "source": "ANIME_SKIP",
                                        "type": {"name": "Preview"},
                                    },
                                    {
                                        "id": "canon-end",
                                        "at": 1420,
                                        "source": "ANIME_SKIP",
                                        "type": {"name": "Canon"},
                                    },
                                ],
                            },
                        ],
                    }
                ]
            }
        }
        request_obj = httpx.Request("POST", "https://anime-skip.test/api/graphql")
        response = httpx.Response(200, json=payload, request=request_obj)
        request = AsyncMock(return_value=response)
        with (
            patch("sources.providers.anime_skip.wait_for_upstream", new=AsyncMock()),
            patch("sources.providers.anime_skip.http_request", new=request),
        ):
            values = await source.load_segments(
                AnimeIdentity({"anilist": "16498"}),
                2,
                episode_length_seconds=1420,
            )
        self.assertEqual(
            [item.kind for item in values], ["opening", "ending", "preview"]
        )
        self.assertEqual(
            [(item.start_seconds, item.end_seconds) for item in values],
            [(90.0, 180.0), (1300.0, 1390.0), (1390.0, 1420.0)],
        )
        self.assertEqual(values[0].source_segment_id, "intro")
        self.assertEqual(values[0].raw_kind, "Intro")
        self.assertEqual(
            request.await_args.args[2], "https://anime-skip.test/api/graphql"
        )
        self.assertEqual(
            request.await_args.kwargs["headers"]["X-Client-ID"], "client-id"
        )
        self.assertEqual(
            request.await_args.kwargs["json"]["variables"]["anilistId"], "16498"
        )

    async def test_show_episode_payload_is_cached_across_episode_lookups(self) -> None:
        source = AnimeSkipSegmentSource(
            client_id="client-id",
            api_url="https://anime-skip.test/api",
            cache_ttl_seconds=3600,
        )
        payload = {
            "data": {
                "findShowsByExternalId": [
                    {
                        "id": "show-id",
                        "episodes": [
                            {
                                "id": "episode-id",
                                "number": "1",
                                "absoluteNumber": None,
                                "baseDuration": 100,
                                "timestamps": [
                                    {
                                        "id": "intro",
                                        "at": 10,
                                        "source": "ANIME_SKIP",
                                        "type": {"name": "Intro"},
                                    },
                                    {
                                        "id": "canon",
                                        "at": 20,
                                        "source": "ANIME_SKIP",
                                        "type": {"name": "Canon"},
                                    },
                                ],
                            }
                        ],
                    }
                ]
            }
        }
        response = httpx.Response(
            200,
            json=payload,
            request=httpx.Request("POST", "https://anime-skip.test/api/graphql"),
        )
        request = AsyncMock(return_value=response)
        with (
            patch("sources.providers.anime_skip.wait_for_upstream", new=AsyncMock()),
            patch("sources.providers.anime_skip.http_request", new=request),
        ):
            first = await source.load_segments(AnimeIdentity({"anilist": "1"}), 1)
            second = await source.load_segments(AnimeIdentity({"anilist": "1"}), 1)
        self.assertEqual(first, second)
        self.assertEqual(request.await_count, 1)


class _MappingResolverStub:
    available = True

    def __init__(self, bahamut_id: str | None) -> None:
        self.bahamut_id = bahamut_id

    def resolve(self, _identity: AnimeIdentity) -> dict[str, str]:
        return {"bahamut": self.bahamut_id} if self.bahamut_id else {}


class BahaAnimeSkipSegmentSourceTests(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def _database(path: Path) -> None:
        with sqlite3.connect(path) as conn:
            conn.executescript(
                """
                CREATE TABLE segments (
                    anime_sn TEXT NOT NULL,
                    episode_number INTEGER NOT NULL,
                    video_sn TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    start_seconds REAL NOT NULL,
                    end_seconds REAL NOT NULL,
                    raw_kind TEXT NOT NULL,
                    PRIMARY KEY (anime_sn, episode_number, video_sn, raw_kind)
                ) WITHOUT ROWID;
                CREATE INDEX segments_lookup_idx
                    ON segments(anime_sn, episode_number, start_seconds, kind);
                """
            )
            conn.executemany(
                """
                INSERT INTO segments(
                    anime_sn, episode_number, video_sn, kind,
                    start_seconds, end_seconds, raw_kind
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    ("113142", 1, "31599", "opening", 1.0, 89.5, "OP"),
                    ("113142", 1, "31599", "ending", 1300.0, 1390.0, "ED"),
                    ("113142", 2, "31600", "opening", 2.0, 90.0, "OP"),
                ],
            )

    async def test_direct_bahamut_id_reads_segments_from_local_sqlite(self) -> None:
        with TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "baha.sqlite3"
            self._database(db_path)
            source = BahaAnimeSkipSegmentSource(db_path=db_path)
            values = await source.load_segments(
                AnimeIdentity({"bahamut": "113142"}),
                1,
                episode_length_seconds=1420,
            )

        self.assertEqual([item.kind for item in values], ["opening", "ending"])
        self.assertEqual(
            [(item.start_seconds, item.end_seconds) for item in values],
            [(1.0, 89.5), (1300.0, 1390.0)],
        )
        self.assertEqual(values[0].source_segment_id, "31599:OP")
        self.assertEqual(values[0].episode_length_seconds, 1420.0)

    async def test_mappings_db_resolution_is_local_and_one_hop(self) -> None:
        with TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "baha.sqlite3"
            self._database(db_path)
            resolver = _MappingResolverStub("113142")
            source = BahaAnimeSkipSegmentSource(
                db_path=db_path,
                mapping_resolver=resolver,  # type: ignore[arg-type]
            )
            values = await source.load_segments(
                AnimeIdentity({"anilist": "130003"}), 2
            )

        self.assertEqual(len(values), 1)
        self.assertEqual(values[0].source_segment_id, "31600:OP")

    async def test_missing_confirmed_bahamut_mapping_returns_empty_without_network(
        self,
    ) -> None:
        with TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "baha.sqlite3"
            self._database(db_path)
            resolver = _MappingResolverStub(None)
            source = BahaAnimeSkipSegmentSource(
                db_path=db_path,
                mapping_resolver=resolver,  # type: ignore[arg-type]
            )
            values = await source.load_segments(
                AnimeIdentity({"anilist": "176314", "mal": "58518"}), 1
            )

        self.assertEqual(values, [])

    async def test_missing_local_database_disables_source(self) -> None:
        with TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "missing.sqlite3"
            source = BahaAnimeSkipSegmentSource(db_path=db_path)
            identity = AnimeIdentity({"bahamut": "113142"})
            self.assertFalse(source.supports_identity(identity))
            self.assertEqual(await source.load_segments(identity, 1), [])


if __name__ == "__main__":
    unittest.main()
