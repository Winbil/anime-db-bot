from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any

from core.cache import BoundedTTLCache
from core.episode_segments import EpisodeSegment
from core.http_client import http_request
from core.identity import AnimeIdentity
from core.settings import SourceSettings, get_settings
from core.source_errors import SourceInvalidResponse
from services.runtime.rate_limits import wait_for_upstream

ANIME_SKIP_API_URL = "https://anime-skip.com/api"
ANIME_SKIP_DISPLAY_NAME = "Anime Skip"
ANIME_SKIP_BACKEND_KEY = "anime_skip"

_QUERY = """
query AnimeSkipEpisodeSegments($anilistId: String!) {
  findShowsByExternalId(service: ANILIST, serviceId: $anilistId) {
    id
    episodes {
      id
      season
      number
      absoluteNumber
      baseDuration
      timestamps {
        id
        at
        source
        type {
          name
        }
      }
    }
  }
}
"""

_KIND_MAP = {
    "branding": "branding",
    "intro": "opening",
    "mixed intro": "mixed_opening",
    "new intro": "opening",
    "recap": "recap",
    "filler": "filler",
    "transition": "transition",
    "credits": "ending",
    "mixed credits": "mixed_ending",
    "new credits": "ending",
    "preview": "preview",
    "title card": "title_card",
}


@dataclass(frozen=True, slots=True)
class _Timestamp:
    id: str | None
    at: float
    source: str
    raw_kind: str


@dataclass(frozen=True, slots=True)
class _Episode:
    id: str | None
    number: str | None
    absolute_number: str | None
    base_duration: float | None
    timestamps: tuple[_Timestamp, ...]


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _positive_integer(value: Any) -> int | None:
    raw = str(value or "").strip()
    if not raw.isdigit():
        return None
    parsed = int(raw)
    return parsed if parsed > 0 else None


def _settings(settings: SourceSettings | None) -> SourceSettings:
    return settings or get_settings().sources


class AnimeSkipSegmentSource:
    """Anime Skip timestamps resolved through a confirmed AniList identity edge.

    Anime Skip stores timestamp *boundaries*: one point starts a section and the
    next point ends it. We normalize those boundaries into ranges before exposing
    them to the rest of the application.
    """

    name = ANIME_SKIP_DISPLAY_NAME
    display_name = ANIME_SKIP_DISPLAY_NAME
    backend_key = ANIME_SKIP_BACKEND_KEY

    def __init__(
        self,
        settings: SourceSettings | None = None,
        *,
        client_id: str | None = None,
        api_url: str | None = None,
        timeout_seconds: float | None = None,
        cache_ttl_seconds: float | None = None,
    ) -> None:
        configured = _settings(settings)
        self._client_id = str(
            configured.anime_skip_client_id if client_id is None else client_id
        ).strip()
        self._api_url = str(
            configured.anime_skip_api_url if api_url is None else api_url
        ).rstrip("/")
        self._timeout_seconds = max(
            1.0,
            float(
                configured.anime_skip_request_timeout_seconds
                if timeout_seconds is None
                else timeout_seconds
            ),
        )
        ttl = (
            configured.anime_skip_cache_ttl_seconds
            if cache_ttl_seconds is None
            else cache_ttl_seconds
        )
        self._cache = BoundedTTLCache[str, tuple[_Episode, ...]](
            max_entries=1000,
            ttl_seconds=max(0.0, float(ttl)),
            name="anime_skip_show_episodes",
        )

    @staticmethod
    def is_enabled(settings: SourceSettings | None = None) -> bool:
        return bool(_settings(settings).anime_skip_client_id.strip())

    def supports_identity(self, identity: AnimeIdentity) -> bool:
        anilist_id = _positive_integer(identity.get("anilist"))
        return bool(self._client_id) and anilist_id is not None

    @staticmethod
    def _parse_episode(raw: Any) -> _Episode | None:
        if not isinstance(raw, dict):
            return None
        timestamps: list[_Timestamp] = []
        for raw_timestamp in raw.get("timestamps") or []:
            if not isinstance(raw_timestamp, dict):
                continue
            at = _number(raw_timestamp.get("at"))
            raw_type = raw_timestamp.get("type")
            raw_kind = (
                str(raw_type.get("name") or "").strip()
                if isinstance(raw_type, dict)
                else ""
            )
            if at is None or not raw_kind:
                continue
            timestamps.append(
                _Timestamp(
                    id=str(raw_timestamp.get("id") or "").strip() or None,
                    at=at,
                    source=str(raw_timestamp.get("source") or "UNKNOWN")
                    .strip()
                    .upper(),
                    raw_kind=raw_kind,
                )
            )
        timestamps.sort(key=lambda item: item.at)
        return _Episode(
            id=str(raw.get("id") or "").strip() or None,
            number=str(raw.get("number") or "").strip() or None,
            absolute_number=str(raw.get("absoluteNumber") or "").strip() or None,
            base_duration=(
                value
                if (value := _number(raw.get("baseDuration"))) is not None and value > 0
                else None
            ),
            timestamps=tuple(timestamps),
        )

    async def _load_episodes(self, anilist_id: str) -> tuple[_Episode, ...]:
        cached = self._cache.get(anilist_id)
        if cached is not None:
            return cached

        await wait_for_upstream("anime_skip", "episode_segments")
        response = await http_request(
            "anime_skip",
            "POST",
            f"{self._api_url}/graphql",
            operation="episode_segments",
            timeout=self._timeout_seconds,
            headers={"X-Client-ID": self._client_id},
            json={
                "query": _QUERY,
                "operationName": "AnimeSkipEpisodeSegments",
                "variables": {"anilistId": anilist_id},
            },
        )
        try:
            payload = response.json()
        except ValueError as exc:
            raise SourceInvalidResponse(
                "Anime Skip returned invalid JSON",
                source="anime_skip",
                operation="episode_segments",
            ) from exc
        if not isinstance(payload, dict):
            raise SourceInvalidResponse(
                "Anime Skip returned an invalid response object",
                source="anime_skip",
                operation="episode_segments",
            )
        errors = payload.get("errors")
        if errors:
            first = errors[0] if isinstance(errors, list) and errors else errors
            message = (
                str(first.get("message") or "GraphQL error")
                if isinstance(first, dict)
                else str(first)
            )
            raise SourceInvalidResponse(
                f"Anime Skip GraphQL error: {message}",
                source="anime_skip",
                operation="episode_segments",
            )
        data = payload.get("data")
        shows = data.get("findShowsByExternalId") if isinstance(data, dict) else None
        if not isinstance(shows, list):
            raise SourceInvalidResponse(
                "Anime Skip response is missing findShowsByExternalId",
                source="anime_skip",
                operation="episode_segments",
            )

        episodes: list[_Episode] = []
        for show in shows:
            if not isinstance(show, dict):
                continue
            for raw_episode in show.get("episodes") or []:
                episode = self._parse_episode(raw_episode)
                if episode is not None:
                    episodes.append(episode)
        frozen = tuple(episodes)
        self._cache.set(anilist_id, frozen)
        return frozen

    @staticmethod
    def _segments_from_episode(
        episode: _Episode,
        *,
        fallback_duration: int | None,
    ) -> list[EpisodeSegment]:
        by_timestamp_source: dict[str, list[_Timestamp]] = {}
        for timestamp in episode.timestamps:
            if timestamp.at < 0:
                continue
            by_timestamp_source.setdefault(timestamp.source, []).append(timestamp)

        source_candidates: list[tuple[int, bool, list[EpisodeSegment]]] = []
        for raw_source, points in by_timestamp_source.items():
            points.sort(key=lambda item: item.at)
            values: list[EpisodeSegment] = []
            for index, point in enumerate(points):
                kind = _KIND_MAP.get(point.raw_kind.casefold())
                if kind is None:
                    continue
                end = points[index + 1].at if index + 1 < len(points) else None
                if end is None:
                    end = episode.base_duration
                if end is None and fallback_duration and fallback_duration > 0:
                    end = float(fallback_duration)
                if end is None or end <= point.at:
                    continue
                values.append(
                    EpisodeSegment(
                        kind=kind,
                        source=ANIME_SKIP_BACKEND_KEY,
                        start_seconds=point.at,
                        end_seconds=end,
                        source_segment_id=point.id,
                        raw_kind=point.raw_kind,
                        episode_length_seconds=episode.base_duration,
                    )
                )
            if values:
                source_candidates.append(
                    (len(values), raw_source == "ANIME_SKIP", values)
                )

        if not source_candidates:
            return []
        return max(source_candidates, key=lambda item: (item[0], item[1]))[2]

    async def load_segments(
        self,
        identity: AnimeIdentity,
        episode_number: int,
        *,
        episode_length_seconds: int | None = None,
    ) -> list[EpisodeSegment]:
        if not self.supports_identity(identity):
            return []
        wanted = int(episode_number)
        if wanted <= 0:
            return []
        anilist_id = str(identity.get("anilist") or "").strip()
        episodes = await self._load_episodes(anilist_id)

        candidates: list[
            tuple[tuple[int, int, int, int, float], list[EpisodeSegment]]
        ] = []
        for episode in episodes:
            number_match = _positive_integer(episode.number) == wanted
            absolute_match = _positive_integer(episode.absolute_number) == wanted
            if not number_match and not absolute_match:
                continue
            segments = self._segments_from_episode(
                episode,
                fallback_duration=episode_length_seconds,
            )
            if episode.base_duration is not None and episode_length_seconds:
                duration_delta = abs(
                    episode.base_duration - float(episode_length_seconds)
                )
            else:
                duration_delta = float("inf")
            score = (
                1 if segments else 0,
                1 if number_match else 0,
                len(segments),
                1 if absolute_match else 0,
                -duration_delta,
            )
            candidates.append((score, segments))

        if not candidates:
            return []
        _, result = max(candidates, key=lambda item: item[0])
        result.sort(
            key=lambda item: (
                item.start_seconds if item.start_seconds is not None else float("inf"),
                item.end_seconds if item.end_seconds is not None else float("inf"),
                item.kind,
            )
        )
        return result
