from __future__ import annotations

from typing import Any

from core.cache import BoundedTTLCache
from core.episode_segments import EpisodeSegment
from core.http_client import http_request
from core.identity import AnimeIdentity
from core.source_errors import SourceInvalidResponse
from services.runtime.rate_limits import wait_for_upstream

ANISKIP_API_URL = "https://api.aniskip.com/v2"
ANISKIP_DISPLAY_NAME = "AniSkip"
ANISKIP_BACKEND_KEY = "aniskip"
ANISKIP_TYPES = ("op", "ed", "mixed-op", "mixed-ed", "recap")
_KIND_MAP = {
    "op": "opening",
    "ed": "ending",
    "mixed-op": "mixed_opening",
    "mixed-ed": "mixed_ending",
    "recap": "recap",
}


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed


class AniSkipSegmentSource:
    """Episode-relative timestamps resolved directly through confirmed MAL IDs."""

    name = ANISKIP_DISPLAY_NAME
    display_name = ANISKIP_DISPLAY_NAME
    backend_key = ANISKIP_BACKEND_KEY

    def __init__(
        self,
        *,
        api_url: str = ANISKIP_API_URL,
        timeout_seconds: float = 15.0,
        cache_ttl_seconds: float = 21600.0,
    ) -> None:
        self._api_url = str(api_url or ANISKIP_API_URL).rstrip("/")
        self._timeout_seconds = max(1.0, float(timeout_seconds))
        self._cache = BoundedTTLCache[tuple[str, int, int], tuple[EpisodeSegment, ...]](
            max_entries=5000,
            ttl_seconds=max(0.0, float(cache_ttl_seconds)),
            name="aniskip_episode_segments",
        )

    @staticmethod
    def supports_identity(identity: AnimeIdentity) -> bool:
        value = str(identity.get("mal") or "").strip()
        return value.isdigit() and int(value) > 0

    async def load_segments(
        self,
        identity: AnimeIdentity,
        episode_number: int,
        *,
        episode_length_seconds: int | None = None,
    ) -> list[EpisodeSegment]:
        mal_id = str(identity.get("mal") or "").strip()
        episode_number = int(episode_number)
        if not self.supports_identity(identity) or episode_number <= 0:
            return []

        episode_length = max(0, int(episode_length_seconds or 0))
        cache_key = (mal_id, episode_number, episode_length)
        cached = self._cache.get(cache_key)
        if cached is not None:
            return list(cached)

        await wait_for_upstream("aniskip", "episode_segments")
        params: list[tuple[str, str | int]] = [
            ("types", kind) for kind in ANISKIP_TYPES
        ]
        if episode_length > 0:
            params.append(("episodeLength", episode_length))
        response = await http_request(
            "aniskip",
            "GET",
            f"{self._api_url}/skip-times/{mal_id}/{episode_number}",
            operation="episode_segments",
            timeout=self._timeout_seconds,
            allowed_statuses={404},
            params=params,
        )
        if response.status_code == 404:
            self._cache.set(cache_key, ())
            return []
        try:
            payload = response.json()
        except ValueError as exc:
            raise SourceInvalidResponse(
                "AniSkip returned invalid JSON",
                source="aniskip",
                operation="episode_segments",
            ) from exc
        if not isinstance(payload, dict):
            raise SourceInvalidResponse(
                "AniSkip returned an invalid response object",
                source="aniskip",
                operation="episode_segments",
            )
        if payload.get("found") is False:
            self._cache.set(cache_key, ())
            return []
        raw_results = payload.get("results")
        if not isinstance(raw_results, list):
            raise SourceInvalidResponse(
                "AniSkip response is missing results",
                source="aniskip",
                operation="episode_segments",
            )

        segments: list[EpisodeSegment] = []
        for raw in raw_results:
            if not isinstance(raw, dict):
                continue
            interval = raw.get("interval")
            if not isinstance(interval, dict):
                continue
            start = _number(interval.get("startTime"))
            end = _number(interval.get("endTime"))
            if start is None or end is None or start < 0 or end < start:
                continue
            raw_kind = str(raw.get("skipType") or "").strip().casefold()
            if not raw_kind:
                continue
            returned_length = _number(raw.get("episodeLength"))
            segments.append(
                EpisodeSegment(
                    kind=_KIND_MAP.get(raw_kind, "other"),
                    source=self.backend_key,
                    start_seconds=start,
                    end_seconds=end,
                    source_segment_id=str(raw.get("skipId") or "").strip() or None,
                    raw_kind=raw_kind,
                    episode_length_seconds=(
                        returned_length
                        if returned_length is not None and returned_length > 0
                        else None
                    ),
                )
            )
        segments.sort(
            key=lambda item: (
                item.start_seconds if item.start_seconds is not None else float("inf"),
                item.end_seconds if item.end_seconds is not None else float("inf"),
                item.kind,
            )
        )
        frozen = tuple(segments)
        self._cache.set(cache_key, frozen)
        return list(frozen)
