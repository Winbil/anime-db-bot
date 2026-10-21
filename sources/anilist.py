from __future__ import annotations

import copy
import html
import os
import re
import time
from datetime import datetime, timezone
from typing import Any

import httpx

from core.http_config import USER_AGENT
from core.models import AnimeRecord, PersonCredit

DEFAULT_ANILIST_GRAPHQL_URL = "https://graphql.anilist.co"
DEFAULT_PEOPLE_MAX_PAGES = 4
DEFAULT_PEOPLE_CACHE_TTL_SECONDS = 21600

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

DETAIL_QUERY = """
query AnimeDetails($idMal: Int!) {
  Media(idMal: $idMal, type: ANIME) {
    id
    idMal
    title { romaji english native }
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
    coverImage { extraLarge large medium }
    siteUrl
    nextAiringEpisode { airingAt episode }
    studios { nodes { name } }
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
          name { full native alternative }
          image { large medium }
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
        node { id name { full native } }
        voiceActors(language: JAPANESE) {
          id
          name { full native alternative }
          image { large medium }
        }
      }
    }
  }
}
"""

_PEOPLE_CACHE: dict[tuple[str, str], tuple[float, list[PersonCredit]]] = {}


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


def _people_cache_ttl() -> int:
    raw = os.getenv(
        "ANILIST_PEOPLE_CACHE_TTL_SECONDS",
        str(DEFAULT_PEOPLE_CACHE_TTL_SECONDS),
    ).strip()
    try:
        return max(0, int(raw))
    except ValueError:
        return DEFAULT_PEOPLE_CACHE_TTL_SECONDS


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


def _name_parts(value: dict[str, Any] | None) -> list[str]:
    value = value or {}
    name = value.get("name") or {}
    return _dedupe([
        _clean_text(name.get("full")),
        _clean_text(name.get("native")),
        *[_clean_text(item) for item in name.get("alternative") or []],
    ])


def _portrait_url(value: dict[str, Any] | None) -> str | None:
    image = (value or {}).get("image") or {}
    return _clean_text(image.get("large")) or _clean_text(image.get("medium")) or None


def _person_credit(value: dict[str, Any] | None, roles: list[str]) -> PersonCredit | None:
    value = value or {}
    names = _name_parts(value)
    if not names:
        return None
    source_id = str(value.get("id") or "").strip()
    portrait = _portrait_url(value)
    return PersonCredit(
        name=names[0],
        roles=_dedupe(roles),
        aliases=names[1:],
        external_ids={"anilist": source_id} if source_id else {},
        portraits={"AniList": [portrait]} if portrait else {},
    )


def _character_name(value: dict[str, Any] | None) -> str:
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
        "User-Agent": USER_AGENT,
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
        raise RuntimeError(f"AniList HTTP {response.status_code}{retry_text}: {preview}")

    try:
        body = response.json()
    except ValueError as exc:
        preview = response.text.replace("\n", " ")[:800]
        raise RuntimeError(f"AniList returned non-JSON response: {preview}") from exc

    if body.get("errors"):
        messages = [error.get("message", str(error)) for error in body["errors"]]
        raise RuntimeError("AniList GraphQL error: " + "; ".join(messages))

    return body.get("data", {})


def _staff_from_connection(connection: dict[str, Any] | None) -> list[PersonCredit]:
    result: list[PersonCredit] = []
    for edge in (connection or {}).get("edges") or []:
        role = _clean_text(edge.get("role"))
        credit = _person_credit(edge.get("node"), [role] if role else [])
        if credit is not None:
            result.append(credit)
    return result


def _voices_from_connection(connection: dict[str, Any] | None) -> list[PersonCredit]:
    result: list[PersonCredit] = []
    for edge in (connection or {}).get("edges") or []:
        character = _character_name(edge.get("node"))
        role = f"Озвучка: {character}" if character and character != "Неизвестно" else "Сэйю"
        for actor in edge.get("voiceActors") or []:
            credit = _person_credit(actor, [role])
            if credit is not None:
                result.append(credit)
    return result


async def _all_staff(media_id: int) -> list[PersonCredit]:
    result: list[PersonCredit] = []
    page = 1
    has_next = True
    while has_next and page <= _people_max_pages():
        data = await _graphql(STAFF_PAGE_QUERY, {"id": media_id, "page": page})
        connection = ((data.get("Media") or {}).get("staff") or {})
        result.extend(_staff_from_connection(connection))
        has_next = bool((connection.get("pageInfo") or {}).get("hasNextPage"))
        page += 1
    return _dedupe_people(result)


async def _all_voices(media_id: int) -> list[PersonCredit]:
    result: list[PersonCredit] = []
    page = 1
    has_next = True
    while has_next and page <= _people_max_pages():
        data = await _graphql(CHARACTERS_PAGE_QUERY, {"id": media_id, "page": page})
        connection = ((data.get("Media") or {}).get("characters") or {})
        result.extend(_voices_from_connection(connection))
        has_next = bool((connection.get("pageInfo") or {}).get("hasNextPage"))
        page += 1
    return _dedupe_people(result)


def _merge_portraits(target: dict[str, list[str]], values: dict[str, list[str]]) -> None:
    for source, urls in values.items():
        target[source] = _dedupe([*target.get(source, []), *(urls or [])])


def _dedupe_people(values: list[PersonCredit]) -> list[PersonCredit]:
    merged: dict[str, PersonCredit] = {}
    for person in values:
        key = person.external_ids.get("anilist") or person.name.casefold()
        existing = merged.get(key)
        if existing is None:
            merged[key] = PersonCredit(
                name=person.name,
                roles=_dedupe(person.roles),
                aliases=_dedupe(person.aliases),
                external_ids=dict(person.external_ids),
                portraits={
                    source: _dedupe(urls)
                    for source, urls in person.portraits.items()
                    if _dedupe(urls)
                },
            )
        else:
            existing.roles = _dedupe([*existing.roles, *person.roles])
            existing.aliases = _dedupe([*existing.aliases, *person.aliases])
            _merge_portraits(existing.portraits, person.portraits)
    return list(merged.values())


def _record(raw: dict[str, Any]) -> AnimeRecord:
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
        (
            _clean_text(cover.get(key))
            for key in ("extraLarge", "large", "medium")
            if _clean_text(cover.get(key))
        ),
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
        studios=_dedupe(
            [node.get("name", "") for node in ((raw.get("studios") or {}).get("nodes") or [])]
        ),
        descriptions={"AniList": description} if description else {},
        posters=[poster] if poster else [],
        urls={"AniList": site_url} if site_url else {},
    )


async def _cached_people(
    media_id: str,
    section: str,
) -> list[PersonCredit]:
    key = (media_id, section)
    now = time.monotonic()
    cached = _PEOPLE_CACHE.get(key)
    if cached is not None and cached[0] > now:
        return copy.deepcopy(cached[1])
    if cached is not None:
        _PEOPLE_CACHE.pop(key, None)

    if section == "staff":
        people = await _all_staff(int(media_id))
    elif section == "voices":
        people = await _all_voices(int(media_id))
    else:
        raise ValueError(f"Unsupported AniList people section: {section}")

    ttl = _people_cache_ttl()
    if ttl > 0:
        _PEOPLE_CACHE[key] = (time.monotonic() + ttl, copy.deepcopy(people))
    return people


class AniListSource:
    name = "AniList"

    async def get_details(
        self,
        mal_id: str,
        known_ids: dict[str, str],
    ) -> AnimeRecord | None:
        mal_id = str(mal_id).strip()
        if not mal_id.isdigit():
            return None

        data = await _graphql(DETAIL_QUERY, {"idMal": int(mal_id)})
        raw = data.get("Media")
        if not raw:
            return None
        if str(raw.get("idMal") or "") != mal_id:
            return None
        return _record(raw)

    async def load_staff(
        self,
        mal_id: str,
        known_ids: dict[str, str],
    ) -> list[PersonCredit]:
        media_id = str(known_ids.get("anilist") or "").strip()
        if not str(mal_id).strip().isdigit() or not media_id.isdigit():
            return []
        return await _cached_people(media_id, "staff")

    async def load_voices(
        self,
        mal_id: str,
        known_ids: dict[str, str],
    ) -> list[PersonCredit]:
        media_id = str(known_ids.get("anilist") or "").strip()
        if not str(mal_id).strip().isdigit() or not media_id.isdigit():
            return []
        return await _cached_people(media_id, "voices")
