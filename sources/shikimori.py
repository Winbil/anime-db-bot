from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any

import httpx

from core.canonicalization import is_primary_voice_role, normalize_key
from core.models import AnimeRecord, PersonCredit

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

PEOPLE_POSTERS_QUERY = """
query PeoplePosters($ids: [ID!]) {
  people(ids: $ids, limit: 50) {
    id
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
    russian = _clean_text(person.get("russian"))
    name = _clean_text(person.get("name"))
    japanese = _clean_text(person.get("japanese"))
    names = _dedupe([russian, name, japanese])
    if not names:
        return None

    preferred = russian or name or japanese
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
    key = normalize_key(value)
    return (
        key == "сэйю"
        or key.startswith("сэйю ")
        or key == "сейю"
        or key.startswith("сейю ")
        or key == "seiyuu"
        or key.startswith("seiyuu ")
        or key == "voice actor"
        or key.startswith("voice actor ")
        or key == "voice acting"
        or key.startswith("voice acting ")
    )


async def _graphql(query: str, variables: dict[str, Any]) -> dict[str, Any]:
    headers = {
        "User-Agent": "anime-db-bot/1.1 (https://github.com/Winbil/anime-db-bot)",
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


def _credits(raw: dict[str, Any], *, voices: bool) -> list[PersonCredit]:
    result: list[PersonCredit] = []
    seen: set[tuple[str, tuple[str, ...]]] = set()

    for entry in raw.get("personRoles") or []:
        person = entry.get("person") or {}
        all_roles = _dedupe(entry.get("rolesRu") or entry.get("rolesEn") or [])

        if voices:
            roles = [role for role in all_roles if is_primary_voice_role(role)]
        else:
            roles = [role for role in all_roles if not _is_any_voice_role(role)]

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


def _attach_person_posters(
    credits: list[PersonCredit],
    raw_people: list[dict[str, Any]],
) -> int:
    by_id = {
        str(person.get("id") or "").strip(): person
        for person in raw_people
        if str(person.get("id") or "").strip()
    }
    attached = 0
    for credit in credits:
        if credit.portraits.get("Shikimori"):
            continue
        person_id = str(credit.external_ids.get("shikimori") or "").strip()
        person = by_id.get(person_id)
        if not person:
            continue
        poster = person.get("poster") or {}
        portrait = _best_poster_url(poster) if isinstance(poster, dict) else None
        if not portrait:
            continue
        credit.portraits["Shikimori"] = [portrait]
        attached += 1
    return attached


async def _enrich_missing_voice_portraits(credits: list[PersonCredit]) -> None:
    """Legacy helper kept for compatibility; the live source enriches voices lazily."""
    missing_ids = _dedupe([
        str(credit.external_ids.get("shikimori") or "").strip()
        for credit in credits
        if not credit.portraits.get("Shikimori")
    ])
    if not missing_ids:
        return

    try:
        for offset in range(0, len(missing_ids), 50):
            ids = missing_ids[offset:offset + 50]
            data = await _graphql(PEOPLE_POSTERS_QUERY, {"ids": ids})
            _attach_person_posters(credits, data.get("people") or [])
    except Exception:
        logging.warning(
            "Could not backfill Shikimori seiyuu portraits",
            exc_info=True,
        )


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

    description = _clean_text(raw.get("description"))

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
        descriptions={"Shikimori": description} if description else {},
        posters=[poster_url] if poster_url else [],
        urls={"Shikimori": url} if url else {},
        staff=_credits(raw, voices=False),
        voices=_credits(raw, voices=True),
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

        # The extended Shikimori source loads character-backed seiyuu only when
        # the user opens the seiyuu section. Do not perform people enrichment
        # during the fast metadata path.
        return _record(raw)
