from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, patch

import httpx

from core.episode_segments import EpisodeSegment
from core.identity import AnimeIdentity
from services.media.episode_segments import EpisodeSegmentService, aggregate_segments
from sources.providers.aniskip import AniSkipSegmentSource


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


if __name__ == "__main__":
    unittest.main()
