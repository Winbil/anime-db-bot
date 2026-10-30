from __future__ import annotations

import asyncio
from datetime import date, datetime
import math
import re
import unicodedata
from typing import Any

from core.cache import BoundedTTLCache
from core.episode_segments import EpisodeSegment
from core.http_client import http_request
from core.identity import AnimeIdentity
from core.models import AnimeRecord
from core.settings import SourceSettings, get_settings
from core.source_errors import SourceInvalidResponse
from services.runtime.rate_limits import wait_for_upstream
from sources.providers.anilist import AniListSource
from sources.providers.mal import MALSource

BAHA_ANIME_SKIP_DISPLAY_NAME = "Baha Anime Skip"
BAHA_ANIME_SKIP_BACKEND_KEY = "baha_anime_skip"

_KIND_MAP = {"OP": "opening", "ED": "ending"}
_NON_WORD_RE = re.compile(r"[^\w]+", re.UNICODE)


def _settings(settings: SourceSettings | None) -> SourceSettings:
    return settings or get_settings().sources


def _positive_integer(value: Any) -> int | None:
    text = str(value or "").strip()
    if not text.isdigit():
        return None
    parsed = int(text)
    return parsed if parsed > 0 else None


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _normalized_name(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).casefold()
    return _NON_WORD_RE.sub("", text)


def _parse_date(value: Any) -> date | None:
    text = str(value or "").strip().replace("/", "-")
    try:
        return datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError:
        return None


class BahaAnimeSkipSegmentSource:
    """Baha Anime Skip ranges resolved through Bahamut's anime/video serials.

    Preferred identity resolution is a confirmed ``bahamut`` edge from mappings.db
    (fed by Wikidata P13424). When that edge is absent, a deliberately strict
    runtime fallback searches Bahamut by trusted MAL/AniList titles and accepts a
    candidate only when year/date, episode count and studio all corroborate it.
    Runtime fallback matches are cached but are never written to mappings.db.
    """

    name = BAHA_ANIME_SKIP_DISPLAY_NAME
    display_name = BAHA_ANIME_SKIP_DISPLAY_NAME
    backend_key = BAHA_ANIME_SKIP_BACKEND_KEY

    def __init__(
        self,
        settings: SourceSettings | None = None,
        *,
        api_url: str | None = None,
        data_url: str | None = None,
        timeout_seconds: float | None = None,
        cache_ttl_seconds: float | None = None,
        fallback_cache_ttl_seconds: float | None = None,
    ) -> None:
        configured = _settings(settings)
        self._settings = configured
        self._api_url = str(api_url or configured.bahamut_api_url).rstrip("/")
        self._data_url = str(data_url or configured.baha_anime_skip_data_url).strip()
        self._timeout_seconds = max(
            1.0,
            float(
                configured.bahamut_request_timeout_seconds
                if timeout_seconds is None
                else timeout_seconds
            ),
        )
        data_ttl = (
            configured.baha_anime_skip_cache_ttl_seconds
            if cache_ttl_seconds is None
            else cache_ttl_seconds
        )
        fallback_ttl = (
            configured.bahamut_fallback_cache_ttl_seconds
            if fallback_cache_ttl_seconds is None
            else fallback_cache_ttl_seconds
        )
        self._data_cache = BoundedTTLCache[str, dict[str, Any]](
            max_entries=1,
            ttl_seconds=max(0.0, float(data_ttl)),
            name="baha_anime_skip_data",
        )
        self._anime_cache = BoundedTTLCache[str, dict[str, Any]](
            max_entries=2000,
            ttl_seconds=max(0.0, float(data_ttl)),
            name="bahamut_anime_details",
        )
        self._fallback_cache = BoundedTTLCache[tuple[tuple[str, str], ...], str](
            max_entries=2000,
            ttl_seconds=max(0.0, float(fallback_ttl)),
            name="bahamut_identity_fallback",
        )

    def supports_identity(self, identity: AnimeIdentity) -> bool:
        if _positive_integer(identity.get("bahamut")) is not None:
            return True
        if _positive_integer(identity.get("anilist")) is not None:
            return True
        return bool(
            self._settings.mal_client_id
            and _positive_integer(identity.get("mal")) is not None
        )

    async def _bahamut_json(
        self,
        path: str,
        *,
        operation: str,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        await wait_for_upstream("bahamut", operation)
        response = await http_request(
            "bahamut",
            "GET",
            f"{self._api_url}/{path.lstrip('/')}",
            operation=operation,
            timeout=self._timeout_seconds,
            params=params,
        )
        try:
            payload = response.json()
        except ValueError as exc:
            raise SourceInvalidResponse(
                "Bahamut returned invalid JSON",
                source="bahamut",
                operation=operation,
            ) from exc
        if not isinstance(payload, dict):
            raise SourceInvalidResponse(
                "Bahamut returned an invalid response object",
                source="bahamut",
                operation=operation,
            )
        return payload

    async def _anime_details(self, anime_sn: str) -> dict[str, Any] | None:
        cached = self._anime_cache.get(anime_sn)
        if cached is not None:
            return cached
        payload = await self._bahamut_json(
            "v4/video.php",
            operation="episodes",
            params={"animeSn": anime_sn},
        )
        data = payload.get("data")
        if not isinstance(data, dict):
            return None
        anime = data.get("anime")
        if not isinstance(anime, dict):
            return None
        returned = _positive_integer(anime.get("animeSn"))
        if returned != int(anime_sn):
            return None
        frozen = {"anime": anime, "video": data.get("video")}
        self._anime_cache.set(anime_sn, frozen)
        return frozen

    async def _reference_records(self, identity: AnimeIdentity) -> list[AnimeRecord]:
        tasks: list[
            asyncio.Future[AnimeRecord | None] | asyncio.Task[AnimeRecord | None]
        ] = []
        if _positive_integer(identity.get("anilist")) is not None:
            tasks.append(
                asyncio.create_task(AniListSource(self._settings).get_details(identity))
            )
        if (
            _positive_integer(identity.get("mal")) is not None
            and self._settings.mal_client_id
        ):
            tasks.append(
                asyncio.create_task(MALSource(self._settings).get_details(identity))
            )
        if not tasks:
            return []
        results = await asyncio.gather(*tasks, return_exceptions=True)
        records: list[AnimeRecord] = []
        for result in results:
            if isinstance(result, AnimeRecord):
                records.append(result)
        return records

    @staticmethod
    def _strict_expectations(records: list[AnimeRecord]) -> dict[str, Any] | None:
        if not records:
            return None
        years: set[int] = set()
        for record in records:
            year = record.aired_on.year if record.aired_on else record.season_year
            if year is not None:
                years.add(int(year))
        episodes = {
            int(record.episodes_total)
            for record in records
            if record.episodes_total and int(record.episodes_total) > 0
        }
        if len(years) != 1 or len(episodes) != 1:
            return None

        studio_sets = [
            {
                _normalized_name(value)
                for value in record.studios
                if _normalized_name(value)
            }
            for record in records
            if record.studios
        ]
        if not studio_sets or any(not values for values in studio_sets):
            return None

        exact_dates: set[date] = set()
        for record in records:
            aired = record.aired_on
            if aired and aired.month is not None and aired.day is not None:
                exact_dates.add(date(aired.year, aired.month, aired.day))

        queries: list[str] = []
        seen: set[str] = set()
        for record in records:
            for title in [*record.titles.values(), *record.synonyms]:
                text = " ".join(str(title or "").split()).strip()
                key = text.casefold()
                if text and key not in seen:
                    seen.add(key)
                    queries.append(text)
                if len(queries) >= 6:
                    break
            if len(queries) >= 6:
                break
        if not queries:
            return None
        return {
            "year": next(iter(years)),
            "episodes": next(iter(episodes)),
            "studio_sets": studio_sets,
            "dates": exact_dates,
            "queries": queries,
        }

    @staticmethod
    def _candidate_matches(anime: dict[str, Any], expected: dict[str, Any]) -> bool:
        total = _positive_integer(anime.get("totalEpisode"))
        if total != expected["episodes"]:
            return False
        started = _parse_date(anime.get("seasonStart"))
        if started is None or started.year != expected["year"]:
            return False
        expected_dates: set[date] = expected["dates"]
        if (
            expected_dates
            and min(abs((started - value).days) for value in expected_dates) > 2
        ):
            return False
        maker = _normalized_name(anime.get("maker"))
        if not maker:
            return False
        for studios in expected["studio_sets"]:
            if maker not in studios:
                return False
        return True

    async def _resolve_fallback(self, identity: AnimeIdentity) -> str | None:
        fingerprint = identity.fingerprint()
        cached = self._fallback_cache.get(fingerprint)
        if cached is not None:
            return cached or None

        records = await self._reference_records(identity)
        expected = self._strict_expectations(records)
        if expected is None:
            self._fallback_cache.set(fingerprint, "")
            return None

        candidate_ids: set[str] = set()
        for query in expected["queries"]:
            payload = await self._bahamut_json(
                "v1/search.php",
                operation="identity",
                params={"kw": query},
            )
            for item in payload.get("anime") or []:
                if not isinstance(item, dict):
                    continue
                candidate_id = _positive_integer(item.get("anime_sn"))
                if candidate_id is not None:
                    candidate_ids.add(str(candidate_id))
            if len(candidate_ids) > 30:
                break

        accepted: list[str] = []
        for candidate in sorted(candidate_ids, key=int):
            details = await self._anime_details(candidate)
            anime = details.get("anime") if details else None
            if isinstance(anime, dict) and self._candidate_matches(anime, expected):
                accepted.append(candidate)
                if len(accepted) > 1:
                    break
        resolved = accepted[0] if len(accepted) == 1 else ""
        self._fallback_cache.set(fingerprint, resolved)
        return resolved or None

    async def _resolve_anime_sn(self, identity: AnimeIdentity) -> str | None:
        direct = _positive_integer(identity.get("bahamut"))
        if direct is not None:
            return str(direct)
        return await self._resolve_fallback(identity)

    @staticmethod
    def _video_sn_for_episode(anime: dict[str, Any], episode_number: int) -> str | None:
        groups = anime.get("episodes")
        if not isinstance(groups, dict):
            return None
        preferred = groups.get("0")
        candidates = preferred if isinstance(preferred, list) else []
        if not candidates:
            candidates = [
                item
                for values in groups.values()
                if isinstance(values, list)
                for item in values
            ]
        matches = {
            str(video_sn)
            for item in candidates
            if isinstance(item, dict)
            and _positive_integer(item.get("episode")) == episode_number
            and (video_sn := _positive_integer(item.get("videoSn"))) is not None
        }
        return next(iter(matches)) if len(matches) == 1 else None

    async def _timestamp_data(self) -> dict[str, Any]:
        cached = self._data_cache.get("data")
        if cached is not None:
            return cached
        await wait_for_upstream("baha_anime_skip", "episode_segments")
        response = await http_request(
            "baha_anime_skip",
            "GET",
            self._data_url,
            operation="episode_segments",
            timeout=self._timeout_seconds,
        )
        try:
            payload = response.json()
        except ValueError as exc:
            raise SourceInvalidResponse(
                "Baha Anime Skip returned invalid JSON",
                source="baha_anime_skip",
                operation="episode_segments",
            ) from exc
        if not isinstance(payload, dict):
            raise SourceInvalidResponse(
                "Baha Anime Skip returned an invalid data object",
                source="baha_anime_skip",
                operation="episode_segments",
            )
        self._data_cache.set("data", payload)
        return payload

    async def load_segments(
        self,
        identity: AnimeIdentity,
        episode_number: int,
        *,
        episode_length_seconds: int | None = None,
    ) -> list[EpisodeSegment]:
        wanted = int(episode_number)
        if wanted <= 0 or not self.supports_identity(identity):
            return []
        anime_sn = await self._resolve_anime_sn(identity)
        if anime_sn is None:
            return []
        details = await self._anime_details(anime_sn)
        anime = details.get("anime") if details else None
        if not isinstance(anime, dict):
            return []
        video_sn = self._video_sn_for_episode(anime, wanted)
        if video_sn is None:
            return []

        data = await self._timestamp_data()
        raw_segments = data.get(video_sn)
        if not isinstance(raw_segments, dict):
            return []
        result: list[EpisodeSegment] = []
        for raw_kind, normalized_kind in _KIND_MAP.items():
            raw_range = raw_segments.get(raw_kind)
            if not isinstance(raw_range, list) or len(raw_range) < 2:
                continue
            start = _number(raw_range[0])
            duration = _number(raw_range[1])
            if start is None or duration is None or start < 0 or duration <= 0:
                continue
            result.append(
                EpisodeSegment(
                    kind=normalized_kind,
                    source=self.backend_key,
                    start_seconds=start,
                    end_seconds=start + duration,
                    source_segment_id=f"{video_sn}:{raw_kind}",
                    raw_kind=raw_kind,
                    episode_length_seconds=(
                        float(episode_length_seconds)
                        if episode_length_seconds and episode_length_seconds > 0
                        else None
                    ),
                )
            )
        result.sort(
            key=lambda item: (
                item.start_seconds if item.start_seconds is not None else float("inf"),
                item.kind,
            )
        )
        return result
