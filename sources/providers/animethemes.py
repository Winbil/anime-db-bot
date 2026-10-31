from __future__ import annotations

import re
from typing import Any

from core.anime_themes import AnimeThemeEntry
from core.cache import BoundedTTLCache
from core.http_client import http_request
from core.identity import AnimeIdentity
from core.settings import SourceSettings, get_settings
from core.source_errors import SourceInvalidResponse
from services.runtime.rate_limits import wait_for_upstream

ANIMETHEMES_API_URL = "https://api.animethemes.moe"
ANIMETHEMES_DISPLAY_NAME = "AnimeThemes"
_EPISODE_TOKEN_RE = re.compile(r"^\s*(\d+)\s*(?:-\s*(\d+)\s*)?$")


def _settings(settings: SourceSettings | None) -> SourceSettings:
    return settings or get_settings().sources


def _positive_integer(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    raw = str(value or "").strip()
    if not raw.isdigit():
        return None
    parsed = int(raw)
    return parsed if parsed > 0 else None


def _episode_ranges(value: Any) -> tuple[tuple[int, int], ...]:
    raw = str(value or "").strip()
    if not raw:
        return ()
    ranges: list[tuple[int, int]] = []
    for token in raw.split(","):
        match = _EPISODE_TOKEN_RE.match(token)
        if match is None:
            continue
        start = int(match.group(1))
        end = int(match.group(2) or start)
        if start <= 0 or end < start:
            continue
        ranges.append((start, end))
    return tuple(ranges)


def _kind(value: Any) -> str | None:
    raw = str(value or "").strip().casefold()
    if raw == "op":
        return "opening"
    if raw == "ed":
        return "ending"
    return None


def _artists(song: dict[str, Any]) -> tuple[str, ...]:
    values: list[str] = []
    seen: set[str] = set()
    for raw in song.get("artists") or []:
        if not isinstance(raw, dict):
            continue
        name = str(raw.get("name") or "").strip()
        key = name.casefold()
        if name and key not in seen:
            seen.add(key)
            values.append(name)
    return tuple(values)


def _video_url(entry: dict[str, Any]) -> str | None:
    candidates = [raw for raw in entry.get("videos") or [] if isinstance(raw, dict)]
    candidates = [
        raw for raw in candidates if str(raw.get("link") or "").startswith("https://")
    ]
    if not candidates:
        return None

    def score(raw: dict[str, Any]) -> tuple[int, int, int, int]:
        return (
            1 if not bool(raw.get("subbed")) else 0,
            1 if bool(raw.get("nc")) else 0,
            _positive_integer(raw.get("resolution")) or 0,
            1 if str(raw.get("source") or "").upper() == "BD" else 0,
        )

    chosen = max(candidates, key=score)
    return str(chosen.get("link") or "").strip() or None


class AnimeThemesSource:
    """Read-only AnimeThemes metadata resolved by confirmed external IDs."""

    name = ANIMETHEMES_DISPLAY_NAME
    display_name = ANIMETHEMES_DISPLAY_NAME

    def __init__(
        self,
        settings: SourceSettings | None = None,
        *,
        api_url: str | None = None,
        timeout_seconds: float | None = None,
        cache_ttl_seconds: float | None = None,
    ) -> None:
        configured = _settings(settings)
        self._api_url = str(
            configured.animethemes_api_url if api_url is None else api_url
        ).rstrip("/")
        self._timeout_seconds = max(
            1.0,
            float(
                configured.animethemes_request_timeout_seconds
                if timeout_seconds is None
                else timeout_seconds
            ),
        )
        ttl = (
            configured.animethemes_cache_ttl_seconds
            if cache_ttl_seconds is None
            else cache_ttl_seconds
        )
        self._cache = BoundedTTLCache[
            tuple[str, str], tuple[AnimeThemeEntry, ...] | None
        ](
            max_entries=1000,
            ttl_seconds=max(0.0, float(ttl)),
            name="animethemes_anime",
        )

    @staticmethod
    def supports_identity(identity: AnimeIdentity) -> bool:
        return any(
            _positive_integer(identity.get(key)) is not None
            for key in ("anilist", "mal")
        )

    @staticmethod
    def _identity_candidates(identity: AnimeIdentity) -> tuple[tuple[str, str], ...]:
        candidates: list[tuple[str, str]] = []
        for key, site in (("anilist", "AniList"), ("mal", "MyAnimeList")):
            value = _positive_integer(identity.get(key))
            if value is not None:
                candidates.append((site, str(value)))
        return tuple(candidates)

    @staticmethod
    def _parse_anime(raw: dict[str, Any]) -> tuple[AnimeThemeEntry, ...]:
        result: list[AnimeThemeEntry] = []
        for raw_theme in raw.get("animethemes") or []:
            if not isinstance(raw_theme, dict):
                continue
            kind = _kind(raw_theme.get("type"))
            if kind is None:
                continue
            slug = str(raw_theme.get("slug") or "").strip()
            sequence = _positive_integer(raw_theme.get("sequence"))
            song_raw = raw_theme.get("song")
            song = song_raw if isinstance(song_raw, dict) else {}
            title = str(song.get("title") or "").strip() or None
            artists = _artists(song)
            theme_id = str(raw_theme.get("id") or "").strip() or None

            for raw_entry in raw_theme.get("animethemeentries") or []:
                if not isinstance(raw_entry, dict) or bool(raw_entry.get("nsfw")):
                    continue
                episodes = str(raw_entry.get("episodes") or "").strip() or None
                result.append(
                    AnimeThemeEntry(
                        kind=kind,
                        slug=slug,
                        title=title,
                        artists=artists,
                        sequence=sequence,
                        episodes=episodes,
                        episode_ranges=_episode_ranges(episodes),
                        version=_positive_integer(raw_entry.get("version")),
                        video_url=_video_url(raw_entry),
                        source_theme_id=theme_id,
                        source_entry_id=(
                            str(raw_entry.get("id") or "").strip() or None
                        ),
                        spoiler=bool(raw_entry.get("spoiler")),
                    )
                )
        return tuple(result)

    async def _load_candidate(
        self,
        site: str,
        external_id: str,
    ) -> tuple[AnimeThemeEntry, ...] | None:
        cache_key = (site, external_id)
        if cache_key in self._cache:
            return self._cache[cache_key]

        await wait_for_upstream("animethemes", "themes")
        response = await http_request(
            "animethemes",
            "GET",
            f"{self._api_url}/anime/",
            operation="themes",
            timeout=self._timeout_seconds,
            params={
                "filter[external_id]": external_id,
                "filter[has]": "resources",
                "filter[site]": site,
                "include": (
                    "animethemes.animethemeentries.videos,"
                    "animethemes.song,animethemes.song.artists"
                ),
                "fields[anime]": "id,name,slug",
                "fields[animetheme]": "id,sequence,slug,type",
                "fields[animethemeentry]": "id,episodes,version,spoiler,nsfw",
                "fields[song]": "id,title",
                "fields[artist]": "id,name",
                "fields[video]": "id,link,nc,resolution,subbed,source",
                "page[size]": 5,
            },
        )
        try:
            payload = response.json()
        except ValueError as exc:
            raise SourceInvalidResponse(
                "AnimeThemes returned invalid JSON",
                source="animethemes",
                operation="themes",
            ) from exc
        if not isinstance(payload, dict):
            raise SourceInvalidResponse(
                "AnimeThemes returned an invalid response object",
                source="animethemes",
                operation="themes",
            )
        raw_anime = payload.get("anime")
        if not isinstance(raw_anime, list):
            raise SourceInvalidResponse(
                "AnimeThemes response is missing anime results",
                source="animethemes",
                operation="themes",
            )
        matches = [item for item in raw_anime if isinstance(item, dict)]
        if len(matches) != 1:
            # Zero results may be retried through another confirmed identity. More
            # than one result is ambiguous and must never be guessed by title.
            self._cache.set(cache_key, None)
            return None
        parsed = self._parse_anime(matches[0])
        self._cache.set(cache_key, parsed)
        return parsed

    async def load_themes(self, identity: AnimeIdentity) -> list[AnimeThemeEntry]:
        if not self.supports_identity(identity):
            return []
        for site, external_id in self._identity_candidates(identity):
            values = await self._load_candidate(site, external_id)
            if values is not None:
                return list(values)
        return []
