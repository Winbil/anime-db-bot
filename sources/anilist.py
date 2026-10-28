from __future__ import annotations

import copy
import html
import re
from datetime import datetime, timezone
from typing import Any

from core.cache import BoundedTTLCache
from core.canonicalization import (
    canonical_genre_token,
    canonical_role_token,
    voice_role_token,
)
from core.http_client import http_request
from core.identity import AnimeIdentity
from core.http_config import USER_AGENT
from core.models import AnimeRecord, CharacterRecord, PersonCredit, PopularityRanking
from core.people_loading import PeopleBatch
from core.settings import SourceSettings, get_settings
from core.temporal import PartialDate, parse_partial_date
from core.source_errors import SourceInvalidResponse
from core.source_keys import SourceKey
from localization import source_value_key

DEFAULT_ANILIST_GRAPHQL_URL = "https://graphql.anilist.co"
DEFAULT_PEOPLE_MAX_PAGES = 4
DEFAULT_PEOPLE_CACHE_TTL_SECONDS = 21600

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
    popularity
    favourites
    rankings { rank type year season allTime }
    stats {
      statusDistribution { status amount }
      scoreDistribution { score amount }
    }
    genres
    isAdult
    coverImage { extraLarge large medium }
    siteUrl
    nextAiringEpisode { airingAt episode }
    studios { nodes { name } }
  }
}
"""

BY_ID_QUERY = """
query AnimeDetailsById($id: Int!) {
  Media(id: $id, type: ANIME) {
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
    popularity
    favourites
    rankings { rank type year season allTime }
    stats {
      statusDistribution { status amount }
      scoreDistribution { score amount }
    }
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
        role
        node {
          id
          name { full native alternative }
          image { large medium }
        }
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

_PEOPLE_CACHE = BoundedTTLCache[tuple[str, str], list[PersonCredit]](max_entries=1000)


def _settings(settings: SourceSettings | None = None) -> SourceSettings:
    return settings or get_settings().sources


def graphql_url(settings: SourceSettings | None = None) -> str:
    return _settings(settings).anilist_api_url or DEFAULT_ANILIST_GRAPHQL_URL


def _people_max_pages(settings: SourceSettings | None = None) -> int:
    return max(1, min(_settings(settings).anilist_people_max_pages, 20))


def _people_cache_ttl(settings: SourceSettings | None = None) -> int:
    return max(0, int(_settings(settings).anilist_people_cache_ttl_seconds))


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).replace("\r", " ").split())


def _clean_description(value: Any) -> str:
    text_value = str(value or "")
    if not text_value:
        return ""
    text_value = re.sub(r"<br\s*/?>", "\n", text_value, flags=re.IGNORECASE)
    text_value = re.sub(r"<[^>]+>", "", text_value)
    text_value = html.unescape(text_value)
    text_value = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", text_value)
    text_value = text_value.replace("~!", "").replace("!~", "")
    lines = [" ".join(line.split()) for line in text_value.splitlines()]
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


def _format_date(value: dict[str, Any] | None) -> PartialDate | None:
    return parse_partial_date(value)


def _format_timestamp(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromtimestamp(int(value), tz=timezone.utc)
    except (TypeError, ValueError, OSError):
        return None


def _name_parts(value: dict[str, Any] | None) -> list[str]:
    value = value or {}
    name = value.get("name") or {}
    return _dedupe(
        [
            _clean_text(name.get("full")),
            _clean_text(name.get("native")),
            *[_clean_text(item) for item in name.get("alternative") or []],
        ]
    )


def _portrait_url(value: dict[str, Any] | None) -> str | None:
    image = (value or {}).get("image") or {}
    return _clean_text(image.get("large")) or _clean_text(image.get("medium")) or None


def _person_credit(
    value: dict[str, Any] | None, roles: list[str]
) -> PersonCredit | None:
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
    return _clean_text(name.get("full")) or _clean_text(name.get("native"))


def _season(value: str | None, year: int | None) -> tuple[str | None, int | None]:
    raw = _clean_text(value)
    season = source_value_key("anilist", "season", raw, default=raw or None)
    return season, int(year) if year else None


def _score(value: Any) -> float | None:
    try:
        return round(float(value) / 10.0, 2) if value is not None else None
    except (TypeError, ValueError):
        return None


def _int(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _status_distribution(value: dict[str, Any] | None) -> dict[str, int]:
    aliases = {
        "CURRENT": "watching",
        "COMPLETED": "completed",
        "PAUSED": "on_hold",
        "DROPPED": "dropped",
        "PLANNING": "planned",
        "REPEATING": "rewatching",
    }
    result: dict[str, int] = {}
    for item in (value or {}).get("statusDistribution") or []:
        key = aliases.get(str(item.get("status") or "").upper())
        amount = _int(item.get("amount"))
        if key and amount is not None and amount >= 0:
            result[key] = amount
    return result


def _score_distribution(value: dict[str, Any] | None) -> dict[int, int]:
    result: dict[int, int] = {}
    for item in (value or {}).get("scoreDistribution") or []:
        raw_score = _int(item.get("score"))
        amount = _int(item.get("amount"))
        if raw_score is None or amount is None or amount < 0:
            continue
        score = max(1, min(10, round(raw_score / 10)))
        result[score] = result.get(score, 0) + amount
    return result


def _rankings(value: list[dict[str, Any]] | None) -> list[PopularityRanking]:
    result: list[PopularityRanking] = []
    for item in value or []:
        rank = _int(item.get("rank"))
        raw_kind = str(item.get("type") or "").upper()
        kind = {"RATED": "rated", "POPULAR": "popular"}.get(raw_kind)
        if rank is None or rank <= 0 or not kind:
            continue
        raw_season = str(item.get("season") or "")
        season = source_value_key(
            "anilist", "season", raw_season, default=raw_season.casefold() or None
        )
        result.append(
            PopularityRanking(
                rank=rank,
                kind=kind,
                year=_int(item.get("year")),
                season=season,
                all_time=bool(item.get("allTime")),
            )
        )
    return result


def _headers(settings: SourceSettings | None = None) -> dict[str, str]:
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": USER_AGENT,
    }
    access_token = _settings(settings).anilist_access_token
    if access_token:
        headers["Authorization"] = f"Bearer {access_token}"
    return headers


async def graphql_request(
    query: str,
    variables: dict[str, Any],
    settings: SourceSettings | None = None,
    *,
    operation: str = "metadata",
) -> dict[str, Any]:
    response = await http_request(
        "anilist",
        "POST",
        graphql_url(settings),
        operation=operation,
        timeout=20.0,
        headers=_headers(settings),
        json={"query": query, "variables": variables},
    )
    try:
        body = response.json()
    except ValueError as exc:
        preview = response.text.replace("\n", " ")[:800]
        raise SourceInvalidResponse(
            f"AniList returned non-JSON response: {preview}",
            source="anilist",
            operation=operation,
        ) from exc

    if body.get("errors"):
        messages = [error.get("message", str(error)) for error in body["errors"]]
        raise SourceInvalidResponse(
            "AniList GraphQL error: " + "; ".join(messages),
            source="anilist",
            operation=operation,
        )

    data = body.get("data", {})
    if not isinstance(data, dict):
        raise SourceInvalidResponse(
            "AniList GraphQL returned an unexpected data payload",
            source="anilist",
            operation=operation,
        )
    return data


def _staff_from_connection(connection: dict[str, Any] | None) -> list[PersonCredit]:
    result: list[PersonCredit] = []
    for edge in (connection or {}).get("edges") or []:
        role = canonical_role_token(_clean_text(edge.get("role")))
        credit = _person_credit(edge.get("node"), [role] if role else [])
        if credit is not None:
            result.append(credit)
    return result


def _characters_from_connection(
    connection: dict[str, Any] | None,
) -> list[CharacterRecord]:
    result: list[CharacterRecord] = []
    role_map = {
        "MAIN": "main",
        "SUPPORTING": "supporting",
        "BACKGROUND": "background",
    }
    for edge in (connection or {}).get("edges") or []:
        node = edge.get("node") or {}
        names = _name_parts(node)
        if not names:
            continue
        preferred = names[0]
        character_id = _clean_text(node.get("id"))
        image = node.get("image") or {}
        portraits = _dedupe(
            [_clean_text(image.get("large")), _clean_text(image.get("medium"))]
        )
        raw_role = _clean_text(edge.get("role")).upper()
        result.append(
            CharacterRecord(
                name=preferred,
                role=role_map.get(raw_role, raw_role.casefold() or None),
                aliases=[
                    name
                    for name in names[1:]
                    if name.casefold() != preferred.casefold()
                ],
                external_ids={"anilist": character_id} if character_id else {},
                portraits={"AniList": portraits} if portraits else {},
            )
        )
    return result


def _dedupe_characters(values: list[CharacterRecord]) -> list[CharacterRecord]:
    result: list[CharacterRecord] = []
    seen: set[str] = set()
    for character in values:
        key = character.external_ids.get("anilist") or character.name.casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(character)
    return result


async def _all_characters(
    media_id: int,
    settings: SourceSettings | None = None,
) -> list[CharacterRecord]:
    result: list[CharacterRecord] = []
    page = 1
    has_next = True
    while has_next and page <= _people_max_pages(settings):
        data = await graphql_request(
            CHARACTERS_PAGE_QUERY,
            {"id": media_id, "page": page},
            settings,
            operation="people",
        )
        connection = (data.get("Media") or {}).get("characters") or {}
        result.extend(_characters_from_connection(connection))
        has_next = bool((connection.get("pageInfo") or {}).get("hasNextPage"))
        page += 1
    return _dedupe_characters(result)


def _voices_from_connection(connection: dict[str, Any] | None) -> list[PersonCredit]:
    result: list[PersonCredit] = []
    for edge in (connection or {}).get("edges") or []:
        character = _character_name(edge.get("node"))
        role = voice_role_token(character or None)
        for actor in edge.get("voiceActors") or []:
            credit = _person_credit(actor, [role])
            if credit is not None:
                result.append(credit)
    return result


async def _all_staff(
    media_id: int,
    settings: SourceSettings | None = None,
) -> list[PersonCredit]:
    result: list[PersonCredit] = []
    page = 1
    has_next = True
    while has_next and page <= _people_max_pages(settings):
        data = await graphql_request(
            STAFF_PAGE_QUERY,
            {"id": media_id, "page": page},
            settings,
            operation="people",
        )
        connection = (data.get("Media") or {}).get("staff") or {}
        result.extend(_staff_from_connection(connection))
        has_next = bool((connection.get("pageInfo") or {}).get("hasNextPage"))
        page += 1
    return _dedupe_people(result)


async def _all_voices(
    media_id: int,
    settings: SourceSettings | None = None,
) -> list[PersonCredit]:
    result: list[PersonCredit] = []
    page = 1
    has_next = True
    while has_next and page <= _people_max_pages(settings):
        data = await graphql_request(
            CHARACTERS_PAGE_QUERY,
            {"id": media_id, "page": page},
            settings,
            operation="people",
        )
        connection = (data.get("Media") or {}).get("characters") or {}
        result.extend(_voices_from_connection(connection))
        has_next = bool((connection.get("pageInfo") or {}).get("hasNextPage"))
        page += 1
    return _dedupe_people(result)


def _merge_portraits(
    target: dict[str, list[str]], values: dict[str, list[str]]
) -> None:
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
    format_raw = raw.get("format") or ""
    status_raw = raw.get("status") or ""
    season, season_year = _season(raw.get("season"), raw.get("seasonYear"))
    status_distribution = _status_distribution(raw.get("stats"))
    score_distribution = _score_distribution(raw.get("stats"))
    rankings = _rankings(raw.get("rankings"))
    all_time_rank = next(
        (item.rank for item in rankings if item.kind == "rated" and item.all_time),
        None,
    )
    all_time_popularity = next(
        (item.rank for item in rankings if item.kind == "popular" and item.all_time),
        None,
    )
    list_users = _int(raw.get("popularity"))
    if list_users is None and status_distribution:
        list_users = sum(status_distribution.values())
    scoring_users = sum(score_distribution.values()) if score_distribution else None

    return AnimeRecord(
        source="AniList",
        source_id=str(raw.get("id") or ""),
        titles=titles,
        synonyms=_dedupe(raw.get("synonyms") or []),
        external_ids=external_ids,
        kind=source_value_key(
            "anilist", "format", format_raw, default=str(format_raw) or None
        ),
        status=source_value_key(
            "anilist", "status", status_raw, default=str(status_raw) or None
        ),
        rating=(
            source_value_key("anilist", "rating", "ADULT", default="adult")
            if raw.get("isAdult")
            else None
        ),
        season=season,
        season_year=season_year,
        episodes_total=episodes_total,
        episodes_aired=episodes_aired,
        duration_minutes=raw.get("duration") or None,
        aired_on=_format_date(raw.get("startDate")),
        released_on=_format_date(raw.get("endDate")),
        next_episode_at=_format_timestamp(next_airing.get("airingAt")),
        score=_score(raw.get("averageScore")),
        rank=all_time_rank,
        popularity_rank=all_time_popularity,
        list_users=list_users,
        scoring_users=scoring_users,
        favorites=_int(raw.get("favourites")),
        status_distribution=status_distribution,
        score_distribution=score_distribution,
        rankings=rankings,
        genres=_dedupe(
            [canonical_genre_token(value) for value in raw.get("genres") or []]
        ),
        studios=_dedupe(
            [
                node.get("name", "")
                for node in ((raw.get("studios") or {}).get("nodes") or [])
            ]
        ),
        descriptions={"AniList": description} if description else {},
        posters=[poster] if poster else [],
        urls={"AniList": site_url} if site_url else {},
    )


async def _cached_people(
    media_id: str,
    section: str,
    settings: SourceSettings | None = None,
) -> list[PersonCredit]:
    key = (media_id, section)
    cached = _PEOPLE_CACHE.get(key)
    if cached is not None:
        return copy.deepcopy(cached)

    if section == "staff":
        people = await _all_staff(int(media_id), settings)
    elif section == "voices":
        people = await _all_voices(int(media_id), settings)
    else:
        raise ValueError(f"Unsupported AniList people section: {section}")

    ttl = _people_cache_ttl(settings)
    if ttl > 0:
        _PEOPLE_CACHE.set(key, copy.deepcopy(people), ttl_seconds=ttl)
    return people


class AniListSource:
    """Identity-native AniList metadata and lazy people source."""

    name = "AniList"
    source_key = SourceKey.ANILIST

    def __init__(self, settings: SourceSettings | None = None) -> None:
        self._settings = _settings(settings)

    async def get_details(self, identity: AnimeIdentity) -> AnimeRecord | None:
        anilist_id = str(identity.get(SourceKey.ANILIST) or "").strip()
        if anilist_id.isdigit():
            data = await graphql_request(
                BY_ID_QUERY,
                {"id": int(anilist_id)},
                self._settings,
            )
            raw = data.get("Media")
            if not raw or str(raw.get("id") or "") != anilist_id:
                return None
            return _record(raw)

        mal_id = str(identity.get(SourceKey.MAL) or "").strip()
        if not mal_id.isdigit():
            return None
        data = await graphql_request(
            DETAIL_QUERY,
            {"idMal": int(mal_id)},
            self._settings,
        )
        raw = data.get("Media")
        if not raw or str(raw.get("idMal") or "") != mal_id:
            return None
        return _record(raw)

    async def load_characters(self, identity: AnimeIdentity) -> list[CharacterRecord]:
        media_id = str(identity.get(SourceKey.ANILIST) or "").strip()
        if not media_id.isdigit():
            return []
        return await _all_characters(int(media_id), self._settings)

    async def load_staff(self, identity: AnimeIdentity) -> list[PersonCredit]:
        media_id = str(identity.get(SourceKey.ANILIST) or "").strip()
        if not media_id.isdigit():
            return []
        return await _cached_people(media_id, "staff", self._settings)

    async def load_voices(self, identity: AnimeIdentity) -> list[PersonCredit]:
        media_id = str(identity.get(SourceKey.ANILIST) or "").strip()
        if not media_id.isdigit():
            return []
        return await _cached_people(media_id, "voices", self._settings)

    async def load_staff_batch(
        self,
        identity: AnimeIdentity,
        *,
        cursor: str | None = None,
        portrait_limit: int = 50,
    ) -> PeopleBatch:
        if cursor is not None:
            return PeopleBatch(complete=True)
        people = await self.load_staff(identity)
        return PeopleBatch(
            people=people,
            complete=True,
            total_count=len(people),
        )

    async def load_voices_batch(
        self,
        identity: AnimeIdentity,
        *,
        cursor: str | None = None,
        portrait_limit: int = 50,
    ) -> PeopleBatch:
        if cursor is not None:
            return PeopleBatch(complete=True)
        people = await self.load_voices(identity)
        return PeopleBatch(
            people=people,
            complete=True,
            total_count=len(people),
        )
