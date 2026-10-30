from __future__ import annotations

import math
from typing import Any

from core.cache import BoundedTTLCache
from core.canonicalization import canonical_genre_token
from core.http_client import http_request
from core.identity import AnimeIdentity
from core.models import (
    AnimeRecord,
    DescriptionDetails,
    EpisodePage,
    EpisodeRecord,
    PopularityStats,
    TrailerRecord,
)
from core.settings import SourceSettings, get_settings
from core.source_errors import SourceInvalidResponse
from core.source_keys import SourceKey
from core.temporal import parse_datetime, parse_partial_date
from localization import source_value_key
from services.runtime.rate_limits import wait_for_upstream

DEFAULT_KITSU_API_URL = "https://kitsu.io/api/edge"
KITSU_API_PAGE_SIZE = 20
KITSU_LOGICAL_EPISODE_PAGE_SIZE = 100

_DETAIL_CACHE = BoundedTTLCache[str, dict[str, Any]](
    max_entries=2000,
    name="kitsu_detail",
)

_MAPPING_SITES = {
    "anidb": "anidb",
    "anilist/anime": "anilist",
    "myanimelist/anime": "mal",
    "imdb": "imdb",
    "thetvdb": "tvdb",
    "thetvdb/series": "tvdb",
    "themoviedb/movie": "tmdb_movie",
    "themoviedb/tv": "tmdb_tv",
}


def _settings(settings: SourceSettings | None = None) -> SourceSettings:
    return settings or get_settings().sources


def _clean(value: Any) -> str:
    return " ".join(str(value or "").replace("\r", " ").split()).strip()


def _int(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _float(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        cleaned = _clean(value)
        key = cleaned.casefold()
        if cleaned and key not in seen:
            seen.add(key)
            result.append(cleaned)
    return result


def _headers() -> dict[str, str]:
    return {
        "Accept": "application/vnd.api+json",
        "Content-Type": "application/vnd.api+json",
    }


def _included_index(body: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    result: dict[tuple[str, str], dict[str, Any]] = {}
    for raw in body.get("included") or []:
        if not isinstance(raw, dict):
            continue
        resource_type = _clean(raw.get("type")).casefold()
        resource_id = _clean(raw.get("id"))
        if resource_type and resource_id:
            result[(resource_type, resource_id)] = raw
    return result


def _relationship_refs(item: dict[str, Any], relationship: str) -> list[dict[str, Any]]:
    raw = ((item.get("relationships") or {}).get(relationship) or {}).get("data")
    if isinstance(raw, dict):
        return [raw]
    if isinstance(raw, list):
        return [value for value in raw if isinstance(value, dict)]
    return []


def _mapping_ids(
    item: dict[str, Any],
    included: dict[tuple[str, str], dict[str, Any]],
) -> dict[str, str]:
    result: dict[str, str] = {}
    kitsu_id = _clean(item.get("id"))
    if kitsu_id:
        result[SourceKey.KITSU.value] = kitsu_id

    for ref in _relationship_refs(item, "mappings"):
        mapping = included.get(
            (_clean(ref.get("type")).casefold(), _clean(ref.get("id")))
        )
        if mapping is None:
            continue
        attrs = mapping.get("attributes") or {}
        provider = _MAPPING_SITES.get(_clean(attrs.get("externalSite")).casefold())
        external_id = _clean(attrs.get("externalId"))
        if provider and external_id:
            result.setdefault(provider, external_id)
    return result


def _titles(attrs: dict[str, Any]) -> dict[str, str]:
    raw = attrs.get("titles") or {}
    values = {
        "english": _clean(raw.get("en")),
        "romaji": _clean(raw.get("en_jp")),
        "japanese": _clean(raw.get("ja_jp")),
    }
    return {key: value for key, value in values.items() if value}


def _synonyms(attrs: dict[str, Any], titles: dict[str, str]) -> list[str]:
    values = [
        _clean(attrs.get("canonicalTitle")),
        *[_clean(value) for value in attrs.get("abbreviatedTitles") or []],
    ]
    title_keys = {value.casefold() for value in titles.values()}
    return [value for value in _dedupe(values) if value.casefold() not in title_keys]


def _best_image(raw: Any) -> str:
    value = raw if isinstance(raw, dict) else {}
    return _clean(
        value.get("original")
        or value.get("large")
        or value.get("medium")
        or value.get("small")
        or value.get("tiny")
    )


def _score(value: Any) -> float | None:
    raw = _float(value)
    if raw is None:
        return None
    return round(raw / 10.0, 2)


def _scoring_users(attrs: dict[str, Any]) -> int | None:
    frequencies = attrs.get("ratingFrequencies") or {}
    if not isinstance(frequencies, dict):
        return None
    total = 0
    found = False
    for value in frequencies.values():
        count = _int(value)
        if count is None or count < 0:
            continue
        total += count
        found = True
    return total if found else None


def _category_titles(
    item: dict[str, Any],
    included: dict[tuple[str, str], dict[str, Any]],
) -> list[str]:
    result: list[str] = []
    for ref in _relationship_refs(item, "categories"):
        category = included.get(
            (_clean(ref.get("type")).casefold(), _clean(ref.get("id")))
        )
        if category is None:
            continue
        title = _clean((category.get("attributes") or {}).get("title"))
        if title:
            result.append(canonical_genre_token(title))
    return _dedupe(result)


def _production_names(
    item: dict[str, Any],
    included: dict[tuple[str, str], dict[str, Any]],
) -> tuple[list[str], list[str]]:
    studios: list[str] = []
    licensors: list[str] = []
    for ref in _relationship_refs(item, "productions"):
        production = included.get(
            (_clean(ref.get("type")).casefold(), _clean(ref.get("id")))
        )
        if production is None:
            continue
        role = _clean((production.get("attributes") or {}).get("role")).casefold()
        company_refs = _relationship_refs(production, "company")
        if not company_refs:
            continue
        company_ref = company_refs[0]
        company = included.get(
            (
                _clean(company_ref.get("type")).casefold(),
                _clean(company_ref.get("id")),
            )
        )
        if company is None:
            continue
        name = _clean((company.get("attributes") or {}).get("name"))
        if not name:
            continue
        if role == "studio":
            studios.append(name)
        elif role == "licensor":
            licensors.append(name)
    return _dedupe(studios), _dedupe(licensors)


def _site_url(item: dict[str, Any]) -> str:
    attrs = item.get("attributes") or {}
    slug = _clean(attrs.get("slug"))
    kitsu_id = _clean(item.get("id"))
    target = slug or kitsu_id
    return f"https://kitsu.app/anime/{target}" if target else ""


def _record(item: dict[str, Any], body: dict[str, Any]) -> AnimeRecord:
    attrs = item.get("attributes") or {}
    included = _included_index(body)
    titles = _titles(attrs)
    studios, licensors = _production_names(item, included)
    status_raw = _clean(attrs.get("status"))
    episode_count = _int(attrs.get("episodeCount"))
    duration = _int(attrs.get("episodeLength"))
    site_url = _site_url(item)
    poster = _best_image(attrs.get("posterImage"))

    return AnimeRecord(
        source="Kitsu",
        source_id=_clean(item.get("id")),
        titles=titles,
        synonyms=_synonyms(attrs, titles),
        external_ids=_mapping_ids(item, included),
        kind=source_value_key(
            "kitsu",
            "subtype",
            _clean(attrs.get("subtype")),
            default=_clean(attrs.get("subtype")) or None,
        ),
        status=source_value_key(
            "kitsu",
            "status",
            status_raw,
            default=status_raw or None,
        ),
        rating=source_value_key(
            "kitsu",
            "rating",
            _clean(attrs.get("ageRating")),
            default=_clean(attrs.get("ageRating")) or None,
        ),
        episodes_total=episode_count,
        episodes_aired=(episode_count if status_raw.casefold() == "finished" else None),
        duration_minutes=duration if duration and duration > 0 else None,
        aired_on=parse_partial_date(_clean(attrs.get("startDate")) or None),
        released_on=parse_partial_date(_clean(attrs.get("endDate")) or None),
        next_episode_at=parse_datetime(_clean(attrs.get("nextRelease")) or None),
        score=_score(attrs.get("averageRating")),
        rank=_int(attrs.get("ratingRank")),
        popularity_rank=_int(attrs.get("popularityRank")),
        list_users=_int(attrs.get("userCount")),
        scoring_users=_scoring_users(attrs),
        favorites=_int(attrs.get("favoritesCount")),
        genres=_category_titles(item, included),
        studios=studios,
        licensors=licensors,
        posters=[poster] if poster else [],
        urls={"Kitsu": site_url} if site_url else {},
    )


def _episode(item: dict[str, Any]) -> EpisodeRecord | None:
    attrs = item.get("attributes") or {}
    number = _int(attrs.get("number"))
    if number is None or number <= 0:
        return None

    raw_titles = attrs.get("titles") or {}
    titles: dict[str, str] = {}
    english = _clean(raw_titles.get("en"))
    canonical = _clean(attrs.get("canonicalTitle"))
    if english:
        titles["english"] = english
    elif canonical:
        titles["english"] = canonical

    length = _int(attrs.get("length"))
    synopsis = _clean(attrs.get("synopsis") or attrs.get("description"))
    return EpisodeRecord(
        number=number,
        source="kitsu",
        backend="kitsu",
        titles=titles,
        aired_at=parse_partial_date(_clean(attrs.get("airdate")) or None),
        duration_seconds=(length * 60 if length and length > 0 else None),
        synopsis=synopsis or None,
        season_number=_int(attrs.get("seasonNumber")),
        episode_number=number,
    )


async def _request_json(
    settings: SourceSettings,
    path: str,
    *,
    operation: str,
    params: dict[str, object] | None = None,
    wait: bool,
) -> dict[str, Any]:
    if wait:
        await wait_for_upstream("kitsu", operation)
    response = await http_request(
        "kitsu",
        "GET",
        f"{settings.kitsu_api_url}{path}",
        operation=operation,
        timeout=settings.kitsu_request_timeout_seconds,
        headers=_headers(),
        params=params,
    )
    try:
        body = response.json()
    except ValueError as exc:
        raise SourceInvalidResponse(
            "Kitsu returned non-JSON response",
            source="kitsu",
            operation=operation,
        ) from exc
    if not isinstance(body, dict):
        raise SourceInvalidResponse(
            "Kitsu returned an unexpected JSON payload",
            source="kitsu",
            operation=operation,
        )
    return body


async def _load_detail(
    kitsu_id: str,
    settings: SourceSettings,
    *,
    operation: str = "metadata",
    wait: bool = False,
) -> dict[str, Any]:
    cached = _DETAIL_CACHE.get(kitsu_id)
    if cached is not None:
        return cached
    body = await _request_json(
        settings,
        f"/anime/{kitsu_id}",
        operation=operation,
        params={"include": "mappings,categories,productions.company"},
        wait=wait,
    )
    item = body.get("data")
    if not isinstance(item, dict) or _clean(item.get("id")) != kitsu_id:
        return {}
    ttl = max(0.0, settings.kitsu_cache_ttl_seconds)
    if ttl > 0:
        _DETAIL_CACHE.set(kitsu_id, body, ttl_seconds=ttl)
    return body


class KitsuSource:
    name = "Kitsu"
    display_name = "Kitsu"
    source_key = SourceKey.KITSU
    backend_key = "kitsu"

    def __init__(self, settings: SourceSettings | None = None) -> None:
        self._settings = _settings(settings)

    @staticmethod
    def _kitsu_id(identity: AnimeIdentity) -> str:
        value = str(identity.get(SourceKey.KITSU) or "").strip()
        return value if value.isdigit() else ""

    def supports_identity(self, identity: AnimeIdentity) -> bool:
        return bool(self._kitsu_id(identity))

    async def get_details(self, identity: AnimeIdentity) -> AnimeRecord | None:
        kitsu_id = self._kitsu_id(identity)
        if not kitsu_id:
            return None
        body = await _load_detail(kitsu_id, self._settings)
        item = body.get("data") if body else None
        return _record(item, body) if isinstance(item, dict) else None

    async def load_popularity(self, identity: AnimeIdentity) -> PopularityStats:
        kitsu_id = self._kitsu_id(identity)
        if not kitsu_id:
            return PopularityStats()
        body = await _load_detail(kitsu_id, self._settings)
        item = body.get("data") if body else None
        if not isinstance(item, dict):
            return PopularityStats()
        attrs = item.get("attributes") or {}
        return PopularityStats(
            rank=_int(attrs.get("ratingRank")),
            popularity_rank=_int(attrs.get("popularityRank")),
            list_users=_int(attrs.get("userCount")),
            scoring_users=_scoring_users(attrs),
            favorites=_int(attrs.get("favoritesCount")),
        )

    async def load_description(self, identity: AnimeIdentity) -> DescriptionDetails:
        kitsu_id = self._kitsu_id(identity)
        if not kitsu_id:
            return DescriptionDetails()
        body = await _load_detail(kitsu_id, self._settings)
        item = body.get("data") if body else None
        if not isinstance(item, dict):
            return DescriptionDetails()
        attrs = item.get("attributes") or {}
        description = _clean(attrs.get("synopsis") or attrs.get("description"))
        return DescriptionDetails(description=description or None)

    async def load_trailers(self, identity: AnimeIdentity) -> list[TrailerRecord]:
        kitsu_id = self._kitsu_id(identity)
        if not kitsu_id:
            return []
        body = await _load_detail(
            kitsu_id,
            self._settings,
            operation="trailers",
            wait=True,
        )
        item = body.get("data") if body else None
        if not isinstance(item, dict):
            return []
        attrs = item.get("attributes") or {}
        youtube_id = _clean(attrs.get("youtubeVideoId"))
        if not youtube_id:
            return []
        return [
            TrailerRecord(
                source="kitsu",
                backend="kitsu",
                title=None,
                kind="trailer",
                hosting="YouTube",
                url=f"https://www.youtube.com/watch?v={youtube_id}",
                embed_url=f"https://www.youtube.com/embed/{youtube_id}",
                thumbnail=f"https://img.youtube.com/vi/{youtube_id}/hqdefault.jpg",
            )
        ]

    async def load_episode_page(
        self,
        identity: AnimeIdentity,
        *,
        page: int = 1,
    ) -> EpisodePage:
        kitsu_id = self._kitsu_id(identity)
        page = max(1, int(page))
        if not kitsu_id:
            return EpisodePage(items=[], page=page, has_next=False)
        logical_offset = (page - 1) * KITSU_LOGICAL_EPISODE_PAGE_SIZE
        raw_items: list[dict[str, Any]] = []
        total: int | None = None
        for chunk_offset in range(
            logical_offset,
            logical_offset + KITSU_LOGICAL_EPISODE_PAGE_SIZE,
            KITSU_API_PAGE_SIZE,
        ):
            body = await _request_json(
                self._settings,
                f"/anime/{kitsu_id}/episodes",
                operation="episodes",
                params={
                    "sort": "number",
                    "page[limit]": KITSU_API_PAGE_SIZE,
                    "page[offset]": chunk_offset,
                },
                wait=True,
            )
            if total is None:
                total = _int((body.get("meta") or {}).get("count"))
            chunk = [raw for raw in body.get("data") or [] if isinstance(raw, dict)]
            raw_items.extend(chunk)
            if not chunk or len(chunk) < KITSU_API_PAGE_SIZE:
                break
            if total is not None and chunk_offset + len(chunk) >= total:
                break

        items = [episode for raw in raw_items if (episode := _episode(raw)) is not None]
        resolved_total = total if total is not None else logical_offset + len(items)
        last_page = max(1, math.ceil(resolved_total / KITSU_LOGICAL_EPISODE_PAGE_SIZE))
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
        kitsu_id = self._kitsu_id(identity)
        number = max(1, int(episode_number))
        if not kitsu_id:
            return None
        body = await _request_json(
            self._settings,
            f"/anime/{kitsu_id}/episodes",
            operation="episodes",
            params={"filter[number]": number, "page[limit]": 1},
            wait=True,
        )
        for raw in body.get("data") or []:
            if not isinstance(raw, dict):
                continue
            episode = _episode(raw)
            if episode is not None and episode.number == number:
                return episode
        return None
