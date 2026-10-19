from __future__ import annotations

import asyncio
import html
import os
import re
from datetime import datetime, timezone
from typing import Any

import httpx

from core.models import AnimeRecord, PersonCredit, SearchCandidate, SourceSearchHit, SourceSearchPage

DEFAULT_ANILIST_GRAPHQL_URL = "https://graphql.anilist.co"
ANILIST_MAX_PAGE_SIZE = 50
ANILIST_PEOPLE_PAGE_SIZE = 25
DEFAULT_PEOPLE_MAX_PAGES = 4

FORMAT_NAMES = {
    "TV": "TV",
    "TV_SHORT": "TV-короткометражка",
    "MOVIE": "фильм",
    "SPECIAL": "спешл",
    "OVA": "OVA",
    "ONA": "ONA",
    "MUSIC": "клип",
}

STATUS_NAMES = {
    "FINISHED": "вышло",
    "RELEASING": "выходит",
    "NOT_YET_RELEASED": "анонсировано",
    "CANCELLED": "отменено",
    "HIATUS": "приостановлено",
}

SEASON_NAMES = {
    "WINTER": "Зима",
    "SPRING": "Весна",
    "SUMMER": "Лето",
    "FALL": "Осень",
}

SEARCH_QUERY = """
query SearchAnime($search: String!, $page: Int!, $perPage: Int!) {
  Page(page: $page, perPage: $perPage) {
    pageInfo {
      hasNextPage
    }
    media(search: $search, type: ANIME) {
      id
      idMal
      title {
        romaji
        english
        native
      }
      synonyms
      seasonYear
      averageScore
    }
  }
}
"""

DETAIL_QUERY = """
query AnimeDetails($id: Int, $idMal: Int) {
  Media(id: $id, idMal: $idMal, type: ANIME) {
    id
    idMal
    title {
      romaji
      english
      native
    }
    synonyms
    format
    status
    description(asHtml: false)
    startDate { year month day }
    endDate { year month day }
    season
    seasonYear
    episodes
    duration
    averageScore
    genres
    isAdult
    coverImage {
      extraLarge
      large
      medium
    }
    siteUrl
    nextAiringEpisode {
      airingAt
      episode
    }
    studios {
      nodes {
        name
      }
    }
    staff(page: 1, perPage: 25) {
      pageInfo { hasNextPage }
      edges {
        role
        node {
          id
          name { full native }
        }
      }
    }
    characters(page: 1, perPage: 25) {
      pageInfo { hasNextPage }
      edges {
        node {
          id
          name { full native }
        }
        voiceActors {
          id
          name { full native }
        }
      }
    }
  }
}
"""

STAFF_PAGE_QUERY = """
query AnimeStaff($id: Int!, $page: Int!) {
  Media(id: $id, type: ANIME) {
    staff(page: $page, perPage: 25) {
      pageInfo { hasNextPage }
      edges {
        role
        node {
          id
          name { full native }
        }
      }
    }
  }
}
"""

CHARACTERS_PAGE_QUERY = """
query AnimeCharacters($id: Int!, $page: Int!) {
  Media(id: $id, type: ANIME) {
    characters(page: $page, perPage: 25) {
      pageInfo { hasNextPage }
      edges {
        node {
          id
          name { full native }
        }
        voiceActors {
          id
          name { full native }
        }
      }
    }
  }
}
"""


def graphql_url() -> str:
    return (
        os.getenv("ANILIST_API_URL", DEFAULT_ANILIST_GRAPHQL_URL).strip()
        or DEFAULT_ANILIST_GRAPHQL_URL
    )


def _people_max_pages() -> int:
    raw = os.getenv("ANILIST_PEOPLE_MAX_PAGES", str(DEFAULT_PEOPLE_MAX_PAGES)).strip()
    try:
        return max(1, min(int(raw), 20))
    except ValueError:
        return DEFAULT_PEOPLE_MAX_PAGES


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).replace("\r", " ").split())


def _clean_description(value: Any) -> str:
    text = str(value or "")
    if not text:
        return ""
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text)
    text = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", text)
    text = text.replace("~!", "").replace("!~", "")
    lines = [" ".join(line.split()) for line in text.splitlines()]
    return "\n".join(line for line in lines if line).strip()


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        value = _clean_text(value)
        key = value.casefold()
        if value and key not in seen:
            seen.add(key)
            result.append(value)
    return result


def _format_date(value: dict[str, Any] | None) -> str | None:
    if not value or not value.get("year"):
        return None
    result = f"{int(value['year']):04d}"
    if value.get("month"):
        result += f"-{int(value['month']):02d}"
    if value.get("day"):
        result += f"-{int(value['day']):02d}"
    return result


def _format_timestamp(value: Any) -> str | None:
    if not value:
        return None
    try:
        return datetime.fromtimestamp(int(value), tz=timezone.utc).isoformat()
    except (TypeError, ValueError, OSError):
        return None


def _person_name(value: dict[str, Any] | None) -> str:
    value = value or {}
    name = value.get("name") or {}
    return _clean_text(name.get("full")) or _clean_text(name.get("native")) or "Неизвестно"


def _season(value: str | None, year: int | None) -> str | None:
    if not value and not year:
        return None
    name = SEASON_NAMES.get(value or "", value or "")
    return " ".join(part for part in (name, str(year) if year else "") if part).strip() or None


def _score(value: Any) -> float | None:
    try:
        return round(float(value) / 10.0, 2) if value is not None else None
    except (TypeError, ValueError):
        return None


def _headers() -> dict[str, str]:
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": "anime-db-bot/0.5 (https://github.com/Winbil/anime-db-bot)",
    }
    access_token = os.getenv("ANILIST_ACCESS_TOKEN", "").strip()
    if access_token:
        headers["Authorization"] = f"Bearer {access_token}"
    return headers


async def _graphql(query: str, variables: dict[str, Any]) -> dict[str, Any]:
    async with httpx.AsyncClient(
        timeout=20.0,
        headers=_headers(),
        follow_redirects=True,
    ) as client:
        response = await client.post(
            graphql_url(),
            json={"query": query, "variables": variables},
        )

    if response.is_error:
        preview = response.text.replace("\n", " ")[:800]
        retry_after = response.headers.get("Retry-After")
        retry_text = f"; retry after {retry_after}s" if retry_after else ""
        raise RuntimeError(
            f"AniList HTTP {response.status_code}{retry_text}: {preview}"
        )

    try:
        body = response.json()
    except ValueError as exc:
        preview = response.text.replace("\n", " ")[:800]
        raise RuntimeError(f"AniList returned non-JSON response: {preview}") from exc

    if body.get("errors"):
        messages = [error.get("message", str(error)) for error in body["errors"]]
        raise RuntimeError("AniList GraphQL error: " + "; ".join(messages))

    return body.get("data", {})


async def _search_raw(query: str, *, page: int, limit: int) -> tuple[list[dict[str, Any]], bool]:
    effective_limit = max(1, min(int(limit), ANILIST_MAX_PAGE_SIZE))
    data = await _graphql(
        SEARCH_QUERY,
        {
            "search": query,
            "page": max(1, int(page)),
            "perPage": effective_limit,
        },
    )
    page_data = data.get("Page") or {}
    return page_data.get("media") or [], bool((page_data.get("pageInfo") or {}).get("hasNextPage"))


async def _get_raw(*, anilist_id: str | None = None, mal_id: str | None = None) -> dict[str, Any] | None:
    variables: dict[str, int | None] = {"id": None, "idMal": None}
    if anilist_id:
        variables["id"] = int(anilist_id)
    elif mal_id:
        variables["idMal"] = int(mal_id)
    else:
        return None

    data = await _graphql(DETAIL_QUERY, variables)
    return data.get("Media")


def _search_hit(raw: dict[str, Any]) -> SourceSearchHit:
    titles = raw.get("title") or {}
    romaji = _clean_text(titles.get("romaji"))
    english = _clean_text(titles.get("english"))
    native = _clean_text(titles.get("native"))
    synonyms = _dedupe(raw.get("synonyms") or [])
    title = english or romaji or native or "Без названия"

    external_ids = {"anilist": str(raw.get("id") or "")}
    if raw.get("idMal"):
        external_ids["mal"] = str(raw["idMal"])

    return SourceSearchHit(
        source="AniList",
        source_id=str(raw.get("id") or ""),
        title=title,
        aliases=_dedupe([romaji, english, native, *synonyms]),
        year=raw.get("seasonYear"),
        external_ids=external_ids,
        score=_score(raw.get("averageScore")),
    )


def _staff_from_connection(connection: dict[str, Any] | None) -> list[PersonCredit]:
    result: list[PersonCredit] = []
    for edge in (connection or {}).get("edges") or []:
        node = edge.get("node") or {}
        name = _person_name(node)
        role = _clean_text(edge.get("role"))
        if name:
            result.append(PersonCredit(name=name, roles=[role] if role else []))
    return result


def _voices_from_connection(connection: dict[str, Any] | None) -> list[PersonCredit]:
    result: list[PersonCredit] = []
    for edge in (connection or {}).get("edges") or []:
        character = _person_name(edge.get("node"))
        role = f"Озвучка: {character}" if character and character != "Неизвестно" else "Озвучка"
        for actor in edge.get("voiceActors") or []:
            name = _person_name(actor)
            if name:
                result.append(PersonCredit(name=name, roles=[role]))
    return result


async def _additional_staff(media_id: int, first_connection: dict[str, Any]) -> list[PersonCredit]:
    result = _staff_from_connection(first_connection)
    has_next = bool((first_connection.get("pageInfo") or {}).get("hasNextPage"))
    page = 2
    max_pages = _people_max_pages()
    while has_next and page <= max_pages:
        data = await _graphql(STAFF_PAGE_QUERY, {"id": media_id, "page": page})
        connection = ((data.get("Media") or {}).get("staff") or {})
        result.extend(_staff_from_connection(connection))
        has_next = bool((connection.get("pageInfo") or {}).get("hasNextPage"))
        page += 1
    return result


async def _additional_voices(media_id: int, first_connection: dict[str, Any]) -> list[PersonCredit]:
    result = _voices_from_connection(first_connection)
    has_next = bool((first_connection.get("pageInfo") or {}).get("hasNextPage"))
    page = 2
    max_pages = _people_max_pages()
    while has_next and page <= max_pages:
        data = await _graphql(CHARACTERS_PAGE_QUERY, {"id": media_id, "page": page})
        connection = ((data.get("Media") or {}).get("characters") or {})
        result.extend(_voices_from_connection(connection))
        has_next = bool((connection.get("pageInfo") or {}).get("hasNextPage"))
        page += 1
    return result


def _dedupe_people(values: list[PersonCredit]) -> list[PersonCredit]:
    merged: dict[str, PersonCredit] = {}
    for person in values:
        key = person.name.casefold()
        existing = merged.get(key)
        if existing is None:
            merged[key] = PersonCredit(name=person.name, roles=_dedupe(person.roles))
        else:
            existing.roles = _dedupe([*existing.roles, *person.roles])
    return list(merged.values())


async def _record(raw: dict[str, Any]) -> AnimeRecord:
    titles_raw = raw.get("title") or {}
    romaji = _clean_text(titles_raw.get("romaji"))
    english = _clean_text(titles_raw.get("english"))
    native = _clean_text(titles_raw.get("native"))

    titles = {
        key: value
        for key, value in {
            "romaji": romaji,
            "english": english,
            "japanese": native,
        }.items()
        if value
    }

    external_ids = {"anilist": str(raw.get("id") or "")}
    if raw.get("idMal"):
        external_ids["mal"] = str(raw["idMal"])

    cover = raw.get("coverImage") or {}
    poster = next(
        (_clean_text(cover.get(key)) for key in ("extraLarge", "large", "medium") if _clean_text(cover.get(key))),
        None,
    )

    next_airing = raw.get("nextAiringEpisode") or {}
    episodes_total = raw.get("episodes") or None
    if raw.get("status") == "FINISHED" and episodes_total:
        episodes_aired = episodes_total
    elif next_airing.get("episode"):
        episodes_aired = max(0, int(next_airing["episode"]) - 1)
    else:
        episodes_aired = None

    media_id = int(raw.get("id"))
    staff_connection = raw.get("staff") or {}
    characters_connection = raw.get("characters") or {}
    staff, voices = await asyncio.gather(
        _additional_staff(media_id, staff_connection),
        _additional_voices(media_id, characters_connection),
    )

    description = _clean_description(raw.get("description"))
    site_url = _clean_text(raw.get("siteUrl"))

    return AnimeRecord(
        source="AniList",
        source_id=str(raw.get("id") or ""),
        titles=titles,
        synonyms=_dedupe(raw.get("synonyms") or []),
        external_ids=external_ids,
        kind=FORMAT_NAMES.get(raw.get("format"), raw.get("format") or None),
        status=STATUS_NAMES.get(raw.get("status"), raw.get("status") or None),
        rating="18+" if raw.get("isAdult") else None,
        season=_season(raw.get("season"), raw.get("seasonYear")),
        episodes_total=episodes_total,
        episodes_aired=episodes_aired,
        duration_minutes=raw.get("duration") or None,
        aired_on=_format_date(raw.get("startDate")),
        released_on=_format_date(raw.get("endDate")),
        next_episode_at=_format_timestamp(next_airing.get("airingAt")),
        score=_score(raw.get("averageScore")),
        genres=_dedupe(raw.get("genres") or []),
        studios=_dedupe([node.get("name", "") for node in ((raw.get("studios") or {}).get("nodes") or [])]),
        descriptions={"AniList": description} if description else {},
        posters=[poster] if poster else [],
        urls={"AniList": site_url} if site_url else {},
        staff=_dedupe_people(staff),
        voices=_dedupe_people(voices),
    )


class AniListSource:
    name = "AniList"

    async def search(
        self,
        query: str,
        *,
        page: int,
        limit: int,
    ) -> SourceSearchPage:
        raw_items, has_next = await _search_raw(query, page=page, limit=limit)
        return SourceSearchPage(
            items=[_search_hit(item) for item in raw_items],
            has_next=has_next,
        )

    async def get_details(self, candidate: SearchCandidate) -> AnimeRecord | None:
        anilist_id = candidate.source_refs.get(self.name) or candidate.external_ids.get("anilist")
        mal_id = candidate.external_ids.get("mal")

        raw = await _get_raw(anilist_id=anilist_id, mal_id=mal_id)
        if raw:
            return await _record(raw)

        raw_items, _ = await _search_raw(candidate.title, page=1, limit=10)
        if not raw_items:
            return None

        selected: dict[str, Any] | None = None
        if candidate.year:
            selected = next(
                (item for item in raw_items if item.get("seasonYear") == candidate.year),
                None,
            )
        selected = selected or raw_items[0]

        raw = await _get_raw(anilist_id=str(selected.get("id") or ""))
        return await _record(raw) if raw else None
