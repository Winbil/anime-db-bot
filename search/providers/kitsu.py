from __future__ import annotations

from typing import Any

from core.http_client import http_request
from core.models import SearchCandidate, SearchPage
from core.settings import SourceSettings, get_settings
from core.source_errors import SourceInvalidResponse
from services.runtime.rate_limits import wait_for_upstream

KITSU_MAX_PAGE_SIZE = 20

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


def _clean(value: Any) -> str:
    return " ".join(str(value or "").replace("\r", " ").split()).strip()


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


def _included_mappings(body: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for raw in body.get("included") or []:
        if (
            not isinstance(raw, dict)
            or _clean(raw.get("type")).casefold() != "mappings"
        ):
            continue
        mapping_id = _clean(raw.get("id"))
        if mapping_id:
            result[mapping_id] = raw
    return result


def _external_ids(
    item: dict[str, Any], mappings: dict[str, dict[str, Any]]
) -> dict[str, str]:
    result: dict[str, str] = {}
    kitsu_id = _clean(item.get("id"))
    if kitsu_id:
        result["kitsu"] = kitsu_id
    refs = ((item.get("relationships") or {}).get("mappings") or {}).get("data") or []
    for ref in refs:
        if not isinstance(ref, dict):
            continue
        mapping = mappings.get(_clean(ref.get("id")))
        if mapping is None:
            continue
        attrs = mapping.get("attributes") or {}
        provider = _MAPPING_SITES.get(_clean(attrs.get("externalSite")).casefold())
        external_id = _clean(attrs.get("externalId"))
        if provider and external_id:
            result.setdefault(provider, external_id)
    return result


def _best_poster(attrs: dict[str, Any]) -> str:
    raw = attrs.get("posterImage") or {}
    return _clean(
        raw.get("original")
        or raw.get("large")
        or raw.get("medium")
        or raw.get("small")
        or raw.get("tiny")
    )


class KitsuSearchProvider:
    name = "Kitsu"

    def __init__(self, settings: SourceSettings | None = None) -> None:
        self._settings = settings or get_settings().sources

    async def search(
        self,
        query: str,
        *,
        page: int,
        limit: int,
    ) -> SearchPage:
        page = max(1, int(page))
        limit = max(1, min(int(limit), KITSU_MAX_PAGE_SIZE))
        await wait_for_upstream("kitsu", "search")
        response = await http_request(
            "kitsu",
            "GET",
            f"{self._settings.kitsu_api_url}/anime",
            operation="search",
            timeout=self._settings.kitsu_request_timeout_seconds,
            headers={
                "Accept": "application/vnd.api+json",
                "Content-Type": "application/vnd.api+json",
            },
            params={
                "filter[text]": query,
                "page[limit]": limit,
                "page[offset]": (page - 1) * limit,
                "include": "mappings",
                "fields[anime]": (
                    "titles,canonicalTitle,abbreviatedTitles,startDate,"
                    "averageRating,posterImage,mappings"
                ),
                "fields[mappings]": "externalSite,externalId",
            },
        )
        try:
            body = response.json()
        except ValueError as exc:
            raise SourceInvalidResponse(
                "Kitsu search returned non-JSON response",
                source="kitsu",
                operation="search",
            ) from exc
        if not isinstance(body, dict):
            raise SourceInvalidResponse(
                "Kitsu search returned an unexpected JSON payload",
                source="kitsu",
                operation="search",
            )

        mapping_index = _included_mappings(body)
        items: list[SearchCandidate] = []
        for raw in body.get("data") or []:
            if not isinstance(raw, dict):
                continue
            kitsu_id = _clean(raw.get("id"))
            if not kitsu_id:
                continue
            attrs = raw.get("attributes") or {}
            titles = attrs.get("titles") or {}
            english = _clean(titles.get("en"))
            romaji = _clean(titles.get("en_jp"))
            native = _clean(titles.get("ja_jp"))
            canonical = _clean(attrs.get("canonicalTitle"))
            title = english or romaji or canonical or native or "Untitled"
            aliases = _dedupe(
                [
                    romaji,
                    english,
                    native,
                    canonical,
                    *[_clean(value) for value in attrs.get("abbreviatedTitles") or []],
                ]
            )
            aliases = [
                value for value in aliases if value.casefold() != title.casefold()
            ]

            year: int | None = None
            start_date = _clean(attrs.get("startDate"))
            if len(start_date) >= 4 and start_date[:4].isdigit():
                year = int(start_date[:4])

            scores: dict[str, float] = {}
            try:
                if attrs.get("averageRating") is not None:
                    scores[self.name] = round(float(attrs["averageRating"]) / 10.0, 2)
            except (TypeError, ValueError):
                pass

            poster = _best_poster(attrs)
            items.append(
                SearchCandidate(
                    title=title,
                    romaji_title=romaji or None,
                    aliases=aliases,
                    year=year,
                    external_ids=_external_ids(raw, mapping_index),
                    scores=scores,
                    posters=[poster] if poster else [],
                )
            )

        return SearchPage(
            items=items,
            page=page,
            page_size=limit,
            has_next=bool((body.get("links") or {}).get("next")),
        )
