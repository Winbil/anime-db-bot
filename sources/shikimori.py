from __future__ import annotations

import html
import os
import re
from datetime import datetime
from typing import Any

import httpx

from core.canonicalization import (
    canonical_genre_token,
    canonical_role_key,
    canonical_role_token,
    is_primary_voice_role,
)
from core.http_config import USER_AGENT
from core.models import AnimeRecord, PersonCredit
from localization import source_value_key

DEFAULT_SHIKIMORI_GRAPHQL_URL = "https://shikimori.io/api/graphql"
DEFAULT_SHIKIMORI_SITE_URL = "https://shikimori.io"

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
    statusesStats { status count }
    scoresStats { score count }
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

PERSON_ROLES_FIELDS = """
    id
    malId
    personRoles {
      rolesRu
      rolesEn
      person {
        id
        name
        russian
        japanese
        isSeyu
        poster {
          originalUrl
          main2xUrl
          mainUrl
          preview2xUrl
          previewUrl
        }
      }
    }
"""

BY_ID_QUERY = f"""
query AnimeById($ids: String!) {{
  animes(ids: $ids, limit: 1) {{
{DETAIL_FIELDS}
  }}
}}
"""

STAFF_QUERY = f"""
query AnimeStaff($ids: String!) {{
  animes(ids: $ids, limit: 1) {{
{PERSON_ROLES_FIELDS}
  }}
}}
"""

_BBCODE_WRAPPED_RE = re.compile(
    r"\[(?P<tag>character|anime|manga|ranobe|person|club|url)"
    r"(?:=[^\]]*)?\](?P<body>.*?)\[/\s*(?P=tag)\s*\]",
    flags=re.IGNORECASE | re.DOTALL,
)
_BBCODE_BREAK_RE = re.compile(r"\[(?:br|hr)\s*/?\]", flags=re.IGNORECASE)
_BBCODE_DECORATION_RE = re.compile(
    r"\[/?(?:b|i|u|s|spoiler|quote|center|left|right|color|size)"
    r"(?:=[^\]]*)?\]",
    flags=re.IGNORECASE,
)
_BBCODE_REMAINING_RE = re.compile(
    r"\[/?[a-z][a-z0-9_-]*(?:=[^\]]*)?\]",
    flags=re.IGNORECASE,
)
_HTML_BREAK_RE = re.compile(r"<br\s*/?>", flags=re.IGNORECASE)
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_SEASON_RE = re.compile(r"^(?P<year>\d{4})[_\s-]+(?P<season>[a-z]+)$", re.IGNORECASE)


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


def _clean_description(value: Any) -> str:
    if value is None:
        return ""

    text_value = str(value).replace("\r", "")
    if not text_value:
        return ""

    text_value = html.unescape(text_value)
    text_value = _HTML_BREAK_RE.sub("\n", text_value)
    text_value = _BBCODE_BREAK_RE.sub("\n", text_value)

    for _ in range(6):
        text_value, count = _BBCODE_WRAPPED_RE.subn(
            lambda match: match.group("body"),
            text_value,
        )
        if not count:
            break

    text_value = _BBCODE_DECORATION_RE.sub("", text_value)
    text_value = _BBCODE_REMAINING_RE.sub("", text_value)
    text_value = _HTML_TAG_RE.sub("", text_value)

    lines = [
        re.sub(r"[ \t]+", " ", line).strip()
        for line in text_value.split("\n")
    ]
    normalized: list[str] = []
    blank = False
    for line in lines:
        if line:
            normalized.append(line)
            blank = False
        elif normalized and not blank:
            normalized.append("")
            blank = True

    return "\n".join(normalized).strip()


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


def _int(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _status_distribution(value: list[dict[str, Any]] | None) -> dict[str, int]:
    aliases = {
        "watching": "watching",
        "completed": "completed",
        "on_hold": "on_hold",
        "dropped": "dropped",
        "planned": "planned",
        "rewatching": "rewatching",
    }
    result: dict[str, int] = {}
    for item in value or []:
        key = aliases.get(_clean_text(item.get("status")).casefold())
        count = _int(item.get("count"))
        if key and count is not None and count >= 0:
            result[key] = count
    return result


def _score_distribution(value: list[dict[str, Any]] | None) -> dict[int, int]:
    result: dict[int, int] = {}
    for item in value or []:
        score = _int(item.get("score"))
        count = _int(item.get("count"))
        if score is None or count is None or count < 0 or not 1 <= score <= 10:
            continue
        result[score] = result.get(score, 0) + count
    return result


def _season(value: Any) -> tuple[str | None, int | None]:
    raw = _clean_text(value)
    if not raw:
        return None, None
    match = _SEASON_RE.match(raw)
    if match:
        season_raw = match.group("season").casefold()
        season = source_value_key("shikimori", "season", season_raw, default=season_raw)
        return season, int(match.group("year"))
    return source_value_key("shikimori", "season", raw, default=raw), None


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


def _person_credit(person: dict[str, Any], roles: list[str]) -> PersonCredit | None:
    name = _clean_text(person.get("name"))
    russian = _clean_text(person.get("russian"))
    japanese = _clean_text(person.get("japanese"))
    names = _dedupe([name, russian, japanese])
    if not names:
        return None

    preferred = name or russian or japanese
    source_id = str(person.get("id") or "").strip()
    poster = person.get("poster") or {}
    portrait = _best_poster_url(poster) if isinstance(poster, dict) else None
    return PersonCredit(
        name=preferred,
        roles=_dedupe(roles),
        aliases=[item for item in names if item.casefold() != preferred.casefold()],
        external_ids={"shikimori": source_id} if source_id else {},
        portraits={"Shikimori": [portrait]} if portrait else {},
    )


def _is_any_voice_role(value: str) -> bool:
    return canonical_role_key(value) == "voice_actor"


async def _graphql(query: str, variables: dict[str, Any]) -> dict[str, Any]:
    headers = {
        "User-Agent": USER_AGENT,
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


async def _get_raw(anime_id: str) -> dict[str, Any] | None:
    data = await _graphql(BY_ID_QUERY, {"ids": anime_id})
    animes = data.get("animes", [])
    return animes[0] if animes else None


async def _get_staff_raw(anime_id: str) -> dict[str, Any] | None:
    data = await _graphql(STAFF_QUERY, {"ids": anime_id})
    animes = data.get("animes", [])
    return animes[0] if animes else None


def _credits(raw: dict[str, Any], *, voices: bool) -> list[PersonCredit]:
    result: list[PersonCredit] = []
    seen: set[tuple[str, tuple[str, ...]]] = set()

    for entry in raw.get("personRoles") or []:
        person = entry.get("person") or {}
        all_roles = _dedupe(entry.get("rolesRu") or entry.get("rolesEn") or [])

        if voices:
            raw_roles = [role for role in all_roles if is_primary_voice_role(role)]
        else:
            raw_roles = [role for role in all_roles if not _is_any_voice_role(role)]
        roles = _dedupe([canonical_role_token(role) for role in raw_roles])

        if not roles:
            continue

        credit = _person_credit(person, roles)
        if credit is None:
            continue
        key = (
            credit.name.casefold(),
            tuple(item.casefold() for item in credit.roles),
        )
        if key in seen:
            continue
        seen.add(key)
        result.append(credit)

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

    description = _clean_description(raw.get("description"))
    kind_raw = raw.get("kind") or ""
    status_raw = raw.get("status") or ""
    rating_raw = raw.get("rating") or ""
    season, season_year = _season(raw.get("season"))
    status_distribution = _status_distribution(raw.get("statusesStats"))
    score_distribution = _score_distribution(raw.get("scoresStats"))

    return AnimeRecord(
        source="Shikimori",
        source_id=str(raw.get("id") or ""),
        titles=titles,
        synonyms=_dedupe(raw.get("synonyms") or []),
        external_ids=external_ids,
        kind=source_value_key("shikimori", "kind", kind_raw, default=str(kind_raw) or None),
        status=source_value_key("shikimori", "status", status_raw, default=str(status_raw) or None),
        rating=source_value_key("shikimori", "rating", rating_raw, default=str(rating_raw) or None),
        season=season,
        season_year=season_year,
        franchise=_clean_text(raw.get("franchise")) or None,
        episodes_total=raw.get("episodes") or None,
        episodes_aired=raw.get("episodesAired") or None,
        duration_minutes=raw.get("duration") or None,
        aired_on=_format_date(raw.get("airedOn")),
        released_on=_format_date(raw.get("releasedOn")),
        next_episode_at=_format_datetime(raw.get("nextEpisodeAt")),
        score=score,
        list_users=sum(status_distribution.values()) if status_distribution else None,
        scoring_users=sum(score_distribution.values()) if score_distribution else None,
        status_distribution=status_distribution,
        score_distribution=score_distribution,
        genres=_dedupe(
            [
                canonical_genre_token(genre.get("name") or genre.get("russian") or "")
                for genre in raw.get("genres") or []
            ]
        ),
        studios=_dedupe([studio.get("name", "") for studio in raw.get("studios") or []]),
        licensors=_dedupe(raw.get("licensors") or []),
        descriptions={"Shikimori": description} if description else {},
        posters=[poster_url] if poster_url else [],
        urls={"Shikimori": url} if url else {},
        staff=[],
        voices=[],
    )


class ShikimoriSource:
    name = "Shikimori"

    async def get_details(
        self,
        mal_id: str,
        known_ids: dict[str, str],
    ) -> AnimeRecord | None:
        mal_id = str(mal_id).strip()
        shikimori_id = str(known_ids.get("shikimori") or "").strip()
        if not mal_id.isdigit() or not shikimori_id.isdigit():
            return None

        raw = await _get_raw(shikimori_id)
        if not raw:
            return None
        if str(raw.get("malId") or "") != mal_id:
            return None
        return _record(raw)

    async def load_staff(
        self,
        mal_id: str,
        known_ids: dict[str, str],
    ) -> list[PersonCredit]:
        mal_id = str(mal_id).strip()
        shikimori_id = str(known_ids.get("shikimori") or "").strip()
        if not mal_id.isdigit() or not shikimori_id.isdigit():
            return []

        raw = await _get_staff_raw(shikimori_id)
        if not raw or str(raw.get("malId") or "") != mal_id:
            return []
        return _credits(raw, voices=False)
