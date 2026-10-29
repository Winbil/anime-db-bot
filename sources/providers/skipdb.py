from __future__ import annotations

import re
from math import ceil
from typing import Any

from core.cache import BoundedTTLCache
from core.http_client import http_request
from core.identity import AnimeIdentity
from core.models import EpisodePage, EpisodeRecord, EpisodeSkipSegment
from core.settings import SourceSettings, get_settings
from core.source_errors import SourceInvalidResponse
from core.source_keys import SourceKey
from services.runtime.rate_limits import wait_for_upstream

DEFAULT_SKIPDB_API_URL = "https://skipdb.tv"
DEFAULT_SKIPDB_SITE_URL = "https://skipdb.tv"
SKIPDB_DISPLAY_NAME = "SkipDB"
SKIPDB_PAGE_SIZE = 100
_SKIP_ORDER = ("intro", "recap", "outro", "preview")
_IMDB_RE = re.compile(r"^tt\d{6,10}$", re.IGNORECASE)
_FINAL_IMDB_RE = re.compile(r"/title/(tt\d{6,10})(?:[/#?]|$)", re.IGNORECASE)


def _settings(settings: SourceSettings | None = None) -> SourceSettings:
    return settings or get_settings().sources


def _clean(value: object) -> str:
    return " ".join(str(value or "").replace("\r", " ").split()).strip()


def _int(value: object) -> int | None:
    if not isinstance(value, (str, int, float)):
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _float(value: object) -> float | None:
    if not isinstance(value, (str, int, float)):
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _selector(season: int | None, episode: int | None) -> int:
    if season is None and episode is None:
        return 1
    if season is None or episode is None or season <= 0 or episode <= 0:
        raise ValueError("SkipDB series episode requires positive season and episode")
    return season * 10_000 + episode


def _coverage_types(raw: object) -> tuple[str, ...]:
    if not isinstance(raw, dict):
        return ()
    result: list[str] = []
    for kind in _SKIP_ORDER:
        counts = raw.get(kind)
        if not isinstance(counts, dict):
            continue
        if (_int(counts.get("approved")) or 0) > 0:
            result.append(kind)
    return tuple(result)


def _episode_from_overview(
    raw: object, imdb_id: str, site_url: str
) -> EpisodeRecord | None:
    if not isinstance(raw, dict):
        return None
    season = _int(raw.get("season"))
    episode = _int(raw.get("episode"))
    try:
        number = _selector(season, episode)
    except ValueError:
        return None
    title = _clean(raw.get("name"))
    runtime_ms = _int(raw.get("runtimeMs"))
    return EpisodeRecord(
        number=number,
        source="imdb",
        backend="skipdb",
        titles={"english": title} if title else {},
        duration_seconds=(
            runtime_ms // 1000 if runtime_ms and runtime_ms > 0 else None
        ),
        urls={"SkipDB": f"{site_url}/title/{imdb_id}"},
        season_number=season,
        episode_number=episode,
        skip_types=_coverage_types(raw.get("coverage")),
        skip_intro_absent=bool(raw.get("hasIntroAbsence")),
    )


def _segment(kind: str, raw: object) -> EpisodeSkipSegment | None:
    if not isinstance(raw, dict):
        return None
    start_ms = _int(raw.get("start_ms"))
    end_ms = _int(raw.get("end_ms"))
    if start_ms is None or start_ms < 0:
        return None
    if end_ms is not None and end_ms < 0:
        return None
    return EpisodeSkipSegment(
        kind=kind,
        start_ms=start_ms,
        end_ms=end_ms,
        match=_clean(raw.get("match")) or None,
        adjusted=bool(raw.get("adjusted")),
        offset_ms=_int(raw.get("offset_ms")) or 0,
        confidence=_float(raw.get("confidence")),
    )


class SkipDBSource:
    """SkipDB episode/skip-timestamp backend keyed by IMDb identity."""

    name = SKIPDB_DISPLAY_NAME
    display_name = SKIPDB_DISPLAY_NAME
    source_key = SourceKey.IMDB
    backend_key = "skipdb"

    def __init__(self, settings: SourceSettings | None = None) -> None:
        self._settings = _settings(settings)
        self._identity_cache = BoundedTTLCache[str, str](
            max_entries=2000, name="skipdb_identity"
        )
        self._title_cache = BoundedTTLCache[str, dict[str, Any]](
            max_entries=1000, name="skipdb_titles"
        )

    @property
    def _api_url(self) -> str:
        return self._settings.skipdb_api_url

    @property
    def _site_url(self) -> str:
        return self._settings.skipdb_site_url

    @property
    def _timeout(self) -> float:
        return self._settings.skipdb_request_timeout_seconds

    @property
    def _cache_ttl(self) -> float:
        return self._settings.skipdb_cache_ttl_seconds

    def supports_identity(self, identity: AnimeIdentity) -> bool:
        imdb = _clean(identity.get("imdb")).lower()
        if _IMDB_RE.fullmatch(imdb):
            return True
        return any(
            _clean(identity.get(key)).isdigit() for key in ("tmdb_tv", "tmdb_movie")
        )

    async def _resolve_tmdb(self, tmdb_id: str, media_type: str) -> str:
        cache_key = f"{media_type}:{tmdb_id}"
        cached = self._identity_cache.get(cache_key)
        if cached is not None:
            return cached
        await wait_for_upstream("skipdb", "identity")
        response = await http_request(
            "skipdb",
            "GET",
            f"{self._site_url}/title/tmdb/{media_type}/{tmdb_id}",
            operation="identity",
            timeout=self._timeout,
            allowed_statuses={404},
        )
        imdb_id = ""
        if response.status_code != 404:
            match = _FINAL_IMDB_RE.search(str(response.url))
            if match:
                imdb_id = match.group(1).lower()
        self._identity_cache.set(cache_key, imdb_id, ttl_seconds=self._cache_ttl)
        return imdb_id

    async def resolve_imdb(self, identity: AnimeIdentity) -> str:
        imdb = _clean(identity.get("imdb")).lower()
        if _IMDB_RE.fullmatch(imdb):
            return imdb
        tmdb_tv = _clean(identity.get("tmdb_tv"))
        if tmdb_tv.isdigit():
            return await self._resolve_tmdb(tmdb_tv, "series")
        tmdb_movie = _clean(identity.get("tmdb_movie"))
        if tmdb_movie.isdigit():
            return await self._resolve_tmdb(tmdb_movie, "movie")
        return ""

    async def _title(
        self, identity: AnimeIdentity
    ) -> tuple[str, dict[str, Any] | None]:
        imdb_id = await self.resolve_imdb(identity)
        if not imdb_id:
            return "", None
        cached = self._title_cache.get(imdb_id)
        if cached is not None:
            return imdb_id, None if cached.get("_missing") else cached
        await wait_for_upstream("skipdb", "episodes")
        response = await http_request(
            "skipdb",
            "GET",
            f"{self._api_url}/api/titles/{imdb_id}",
            operation="episodes",
            timeout=self._timeout,
            allowed_statuses={404},
            headers={"Accept": "application/json"},
        )
        if response.status_code == 404:
            self._title_cache.set(
                imdb_id, {"_missing": True}, ttl_seconds=min(self._cache_ttl, 3600.0)
            )
            return imdb_id, None
        try:
            body = response.json()
        except ValueError as exc:
            raise SourceInvalidResponse(
                "SkipDB title endpoint returned non-JSON response",
                source="skipdb",
                operation="episodes",
            ) from exc
        if not isinstance(body, dict):
            raise SourceInvalidResponse(
                "SkipDB title endpoint returned an unexpected payload",
                source="skipdb",
                operation="episodes",
            )
        self._title_cache.set(imdb_id, body, ttl_seconds=self._cache_ttl)
        return imdb_id, body

    async def load_episode_page(
        self,
        identity: AnimeIdentity,
        *,
        page: int = 1,
    ) -> EpisodePage:
        page = max(1, int(page))
        imdb_id, title = await self._title(identity)
        if not imdb_id or title is None:
            return EpisodePage(items=[], page=page, last_visible_page=1, has_next=False)
        raw_episodes = title.get("episodes")
        episodes = [
            episode
            for raw in (raw_episodes if isinstance(raw_episodes, list) else [])
            if (episode := _episode_from_overview(raw, imdb_id, self._site_url))
            is not None
        ]
        if not episodes and _clean(title.get("media_type")).casefold() == "movie":
            episodes = [
                EpisodeRecord(
                    number=1,
                    source="imdb",
                    backend="skipdb",
                    titles={"english": _clean(title.get("name"))}
                    if _clean(title.get("name"))
                    else {},
                    urls={"SkipDB": f"{self._site_url}/title/{imdb_id}"},
                )
            ]
        start = (page - 1) * SKIPDB_PAGE_SIZE
        items = episodes[start : start + SKIPDB_PAGE_SIZE]
        last_page = max(1, ceil(len(episodes) / SKIPDB_PAGE_SIZE))
        return EpisodePage(
            items=items,
            page=page,
            last_visible_page=last_page,
            has_next=page < last_page,
        )

    async def load_episode(
        self,
        identity: AnimeIdentity,
        episode_number: int,
    ) -> EpisodeRecord | None:
        imdb_id, title = await self._title(identity)
        if not imdb_id or title is None:
            return None
        target: EpisodeRecord | None = None
        raw_episodes = title.get("episodes")
        for raw in raw_episodes if isinstance(raw_episodes, list) else []:
            candidate = _episode_from_overview(raw, imdb_id, self._site_url)
            if candidate is not None and candidate.number == int(episode_number):
                target = candidate
                break
        if target is None and _clean(title.get("media_type")).casefold() == "movie":
            target = EpisodeRecord(
                number=1,
                source="imdb",
                backend="skipdb",
                titles={"english": _clean(title.get("name"))}
                if _clean(title.get("name"))
                else {},
                urls={"SkipDB": f"{self._site_url}/title/{imdb_id}"},
            )
        if target is None:
            return None

        params: dict[str, object] = {"imdb_id": imdb_id}
        if target.season_number is not None and target.episode_number is not None:
            params["season"] = target.season_number
            params["episode"] = target.episode_number
        if target.duration_seconds:
            params["duration"] = target.duration_seconds

        await wait_for_upstream("skipdb", "episode")
        response = await http_request(
            "skipdb",
            "GET",
            f"{self._api_url}/api/segments",
            operation="episode",
            timeout=self._timeout,
            params=params,
            headers={"Accept": "application/json"},
        )
        try:
            body = response.json()
        except ValueError as exc:
            raise SourceInvalidResponse(
                "SkipDB segments endpoint returned non-JSON response",
                source="skipdb",
                operation="episode",
            ) from exc
        if not isinstance(body, dict):
            raise SourceInvalidResponse(
                "SkipDB segments endpoint returned an unexpected payload",
                source="skipdb",
                operation="episode",
            )
        raw_segments = body.get("segments")
        segments: dict[str, EpisodeSkipSegment] = {}
        intro_absent = target.skip_intro_absent
        if isinstance(raw_segments, dict):
            for kind in _SKIP_ORDER:
                segment = _segment(kind, raw_segments.get(kind))
                if segment is None:
                    continue
                if kind == "intro" and segment.start_ms == 0 and segment.end_ms == 0:
                    intro_absent = True
                    continue
                segments[kind] = segment
        target.skip_segments = segments
        target.skip_types = tuple(kind for kind in _SKIP_ORDER if kind in segments)
        target.skip_intro_absent = intro_absent
        return target
