from __future__ import annotations

import os
from datetime import datetime
from typing import Any

import httpx

from core.models import AnimeRecord, PersonCredit, SearchCandidate, SourceSearchHit, SourceSearchPage

DEFAULT_SHIKIMORI_GRAPHQL_URL = "https://shikimori.io/api/graphql"
DEFAULT_SHIKIMORI_SITE_URL = "https://shikimori.io"
SHIKIMORI_MAX_PAGE_SIZE = 50

SEARCH_FIELDS = """
    id
    malId
    name
    russian
    english
    japanese
    synonyms
    score
    airedOn { year }
"""

DETAIL_FIELDS = """
    id
    malId
    name
    russian
    english
    japanese
    synonyms
    licenseNameRu
    kind
    score
    status
    rating
    season
    episodes
    episodesAired
    duration
    franchise
    airedOn { year month day date }
    releasedOn { year month day date }
    nextEpisodeAt
    genres { id name russian kind }
    studios { id name }
    licensors
    personRoles {
      rolesRu
      rolesEn
      person { id name russian japanese isSeyu }
    }
    description
    poster {
      originalUrl
      main2xUrl
      mainUrl
      preview2xUrl
      previewUrl
    }
    url
"""

BY_ID_QUERY = f"""
query AnimeById($ids: String!) {{
  animes(ids: $ids, limit: 1) {{
{DETAIL_FIELDS}
  }}
}}
"""

STATUS_NAMES = {
    "anons": "анонсировано",
    "ongoing": "выходит",
    "released": "вышло",
}

KIND_NAMES = {
    "tv": "TV",
    "movie": "фильм",
    "ova": "OVA",
    "ona": "ONA",
    "special": "спешл",
    "tv_special": "TV-спешл",
    "music": "клип",
    "pv": "PV",
    "cm": "реклама",
}

RATING_NAMES = {
    "none": "без рейтинга",
    "g": "G",
    "pg": "PG",
    "pg_13": "PG-13",
    "r": "R-17+",
    "r_plus": "R+",
    "rx": "Rx",
}


def graphql_url() -> str:
    return (
        os.getenv("SHIKIMORI_API_URL", DEFAULT_SHIKIMORI_GRAPHQL_URL).strip()
        or DEFAULT_SHIKIMORI_GRAPHQL_URL
    )


def site_url() -> str:
    return (
        os.getenv("SHIKIMORI_SITE_URL", DEFAULT_SHIKIMORI_SITE_URL).strip().rstrip("/")
        or DEFAULT_SHIKIMORI_SITE_URL
    )


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).replace("\r", " ").split())


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
    if not value:
        return None
    if value.get("date"):
        return str(value["date"])

    year, month, day = value.get("year"), value.get("month"), value.get("day")
    if not year:
        return None

    result = f"{year:04d}"
    if month:
        result += f"-{month:02d}"
    if day:
        result += f"-{day:02d}"
    return result


def _format_datetime(value: str | None) -> str | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt.isoformat()
    except ValueError:
        return value


def _person_name(person: dict[str, Any]) -> str:
    russian = _clean_text(person.get("russian"))
    name = _clean_text(person.get("name"))
    japanese = _clean_text(person.get("japanese"))
    preferred = russian or name or japanese or "Неизвестно"
    extras = [
        item
        for item in _dedupe([name, japanese])
        if item.casefold() != preferred.casefold()
    ]
    return f"{preferred} ({', '.join(extras)})" if extras else preferred


def _best_poster_url(poster: dict[str, Any]) -> str | None:
    for field in (
        "originalUrl",
        "main2xUrl",
        "mainUrl",
        "preview2xUrl",
        "previewUrl",
    ):
        value = _clean_text(poster.get(field))
        if value:
            return value
    return None


async def _graphql(query: str, variables: dict[str, Any]) -> dict[str, Any]:
    headers = {
        "User-Agent": "anime-db-bot/0.4 (https://github.com/Winbil/anime-db-bot)",
        "Accept": "application/json",
    }

    async with httpx.AsyncClient(
        timeout=15.0,
        headers=headers,
        follow_redirects=True,
    ) as client:
        response = await client.post(
            graphql_url(),
            json={"query": query, "variables": variables},
        )

    if response.is_error:
        preview = response.text.replace("\n", " ")[:800]
        raise RuntimeError(
            f"Shikimori HTTP {response.status_code} from {response.url}: {preview}"
        )

    try:
        body = response.json()
    except ValueError as exc:
        preview = response.text.replace("\n", " ")[:800]
        raise RuntimeError(
            f"Shikimori returned non-JSON response from {response.url}: {preview}"
        ) from exc

    if body.get("errors"):
        messages = [error.get("message", str(error)) for error in body["errors"]]
        raise RuntimeError("Shikimori GraphQL error: " + "; ".join(messages))

    return body.get("data", {})


def _search_query(page: int, limit: int) -> str:
    page = max(1, int(page))
    limit = max(1, min(int(limit), SHIKIMORI_MAX_PAGE_SIZE))
    return f"""
query SearchAnime($search: String!) {{
  animes(search: $search, page: {page}, limit: {limit}, order: popularity) {{
{SEARCH_FIELDS}
  }}
}}
"""


async def _search_raw(query: str, *, page: int, limit: int) -> list[dict[str, Any]]:
    data = await _graphql(_search_query(page, limit), {"search": query})
    return data.get("animes", [])


async def _get_raw(anime_id: str) -> dict[str, Any] | None:
    data = await _graphql(BY_ID_QUERY, {"ids": anime_id})
    animes = data.get("animes", [])
    return animes[0] if animes else None


def _search_hit(raw: dict[str, Any]) -> SourceSearchHit:
    russian = _clean_text(raw.get("russian"))
    romaji = _clean_text(raw.get("name"))
    english = _clean_text(raw.get("english"))
    japanese = _clean_text(raw.get("japanese"))
    synonyms = _dedupe(raw.get("synonyms") or [])
    title = russian or romaji or english or japanese or "Без названия"

    external_ids = {"shikimori": str(raw.get("id") or "")}
    if raw.get("malId"):
        external_ids["mal"] = str(raw["malId"])

    score: float | None = None
    try:
        if raw.get("score") not in (None, ""):
            score = float(raw["score"])
    except (TypeError, ValueError):
        pass

    return SourceSearchHit(
        source="Shikimori",
        source_id=str(raw.get("id") or ""),
        title=title,
        aliases=_dedupe([romaji, english, japanese, *synonyms]),
        year=(raw.get("airedOn") or {}).get("year"),
        external_ids=external_ids,
        score=score,
    )


def _credits(raw: dict[str, Any], *, voices: bool) -> list[PersonCredit]:
    result: list[PersonCredit] = []
    seen: set[tuple[str, tuple[str, ...]]] = set()

    for role in raw.get("personRoles") or []:
        person = role.get("person") or {}
        if bool(person.get("isSeyu")) != voices:
            continue

        roles = _dedupe(role.get("rolesRu") or role.get("rolesEn") or [])
        name = _person_name(person)
        key = (name.casefold(), tuple(item.casefold() for item in roles))
        if key in seen:
            continue
        seen.add(key)
        result.append(PersonCredit(name=name, roles=roles))

    return result


def _record(raw: dict[str, Any]) -> AnimeRecord:
    russian = _clean_text(raw.get("russian"))
    romaji = _clean_text(raw.get("name"))
    english = _clean_text(raw.get("english"))
    japanese = _clean_text(raw.get("japanese"))
    licensed_ru = _clean_text(raw.get("licenseNameRu"))

    titles = {
        key: value
        for key, value in {
            "russian": russian,
            "romaji": romaji,
            "english": english,
            "japanese": japanese,
            "licensed_ru": licensed_ru,
        }.items()
        if value
    }

    external_ids = {"shikimori": str(raw.get("id") or "")}
    if raw.get("malId"):
        external_ids["mal"] = str(raw["malId"])

    url = _clean_text(raw.get("url"))
    if url.startswith("/"):
        url = f"{site_url()}{url}"

    poster = raw.get("poster") or {}
    poster_url = _best_poster_url(poster) if isinstance(poster, dict) else None

    score: float | None = None
    try:
        if raw.get("score") not in (None, ""):
            score = float(raw["score"])
    except (TypeError, ValueError):
        pass

    return AnimeRecord(
        source="Shikimori",
        source_id=str(raw.get("id") or ""),
        titles=titles,
        synonyms=_dedupe(raw.get("synonyms") or []),
        external_ids=external_ids,
        kind=KIND_NAMES.get(raw.get("kind"), raw.get("kind") or None),
        status=STATUS_NAMES.get(raw.get("status"), raw.get("status") or None),
        rating=RATING_NAMES.get(raw.get("rating"), raw.get("rating") or None),
        season=_clean_text(raw.get("season")) or None,
        franchise=_clean_text(raw.get("franchise")) or None,
        episodes_total=raw.get("episodes") or None,
        episodes_aired=raw.get("episodesAired") or None,
        duration_minutes=raw.get("duration") or None,
        aired_on=_format_date(raw.get("airedOn")),
        released_on=_format_date(raw.get("releasedOn")),
        next_episode_at=_format_datetime(raw.get("nextEpisodeAt")),
        score=score,
        genres=_dedupe(
            [genre.get("russian") or genre.get("name") or "" for genre in raw.get("genres") or []]
        ),
        studios=_dedupe([studio.get("name", "") for studio in raw.get("studios") or []]),
        licensors=_dedupe(raw.get("licensors") or []),
        descriptions={"Shikimori": _clean_text(raw.get("description"))}
        if _clean_text(raw.get("description"))
        else {},
        posters=[poster_url] if poster_url else [],
        urls={"Shikimori": url} if url else {},
        staff=_credits(raw, voices=False),
        voices=_credits(raw, voices=True),
    )


class ShikimoriSource:
    name = "Shikimori"

    async def search(
        self,
        query: str,
        *,
        page: int,
        limit: int,
    ) -> SourceSearchPage:
        effective_limit = max(1, min(int(limit), SHIKIMORI_MAX_PAGE_SIZE))
        raw_items = await _search_raw(query, page=page, limit=effective_limit)
        return SourceSearchPage(
            items=[_search_hit(item) for item in raw_items],
            has_next=len(raw_items) >= effective_limit,
        )

    async def get_details(self, candidate: SearchCandidate) -> AnimeRecord | None:
        source_id = candidate.source_refs.get(self.name)

        if not source_id:
            raw_matches = await _search_raw(candidate.title, page=1, limit=10)
            if not raw_matches:
                return None

            mal_id = candidate.external_ids.get("mal")
            if mal_id:
                for raw in raw_matches:
                    if str(raw.get("malId") or "") == mal_id:
                        source_id = str(raw.get("id") or "")
                        break

            if not source_id and candidate.year:
                for raw in raw_matches:
                    if (raw.get("airedOn") or {}).get("year") == candidate.year:
                        source_id = str(raw.get("id") or "")
                        break

            if not source_id:
                source_id = str(raw_matches[0].get("id") or "")

        if not source_id:
            return None

        raw = await _get_raw(source_id)
        return _record(raw) if raw else None
