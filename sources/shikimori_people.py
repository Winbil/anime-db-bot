from __future__ import annotations

import logging
from typing import Any

import httpx

from core.canonicalization import is_primary_voice_role, normalize_key
from core.models import AnimeRecord, PersonCredit
from sources.shikimori import (
    ShikimoriSource as BaseShikimoriSource,
    _best_poster_url,
    _dedupe,
    _graphql,
    _person_credit,
    site_url,
)


VOICE_ROLES_QUERY = """
query AnimeVoiceRoles($ids: String!) {
  animes(ids: $ids, limit: 1) {
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
  }
}
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


def _is_original_voice_role(value: str) -> bool:
    """Recognize original/Japanese voice labels used by Shikimori."""
    if is_primary_voice_role(value):
        return True

    key = normalize_key(value)
    if not key:
        return False

    if key == "japanese":
        return True
    if "japanese" in key and "voice" in key:
        return True
    if "япон" in key and ("озвуч" in key or "сэйю" in key or "сейю" in key):
        return True

    return key in {
        "seiyu",
        "japanese seiyuu",
        "japanese seiyu",
        "japanese voice actor",
        "japanese voice acting",
    }


def _voice_credits(raw: dict[str, Any]) -> list[PersonCredit]:
    """Fallback parser for the GraphQL personRoles representation."""
    result: list[PersonCredit] = []
    seen: set[tuple[str, tuple[str, ...]]] = set()

    for entry in raw.get("personRoles") or []:
        all_roles = _dedupe([
            *(entry.get("rolesRu") or []),
            *(entry.get("rolesEn") or []),
        ])
        roles = [role for role in all_roles if _is_original_voice_role(role)]
        if not roles:
            continue

        credit = _person_credit(entry.get("person") or {}, ["Сэйю"])
        if credit is None:
            continue

        person_id = str(credit.external_ids.get("shikimori") or "").strip()
        key = (
            person_id or credit.name.casefold(),
            tuple(role.casefold() for role in roles),
        )
        if key in seen:
            continue
        seen.add(key)
        result.append(credit)

    return result


async def _reload_voice_credits(anime_id: str) -> list[PersonCredit]:
    data = await _graphql(VOICE_ROLES_QUERY, {"ids": anime_id})
    animes = data.get("animes") or []
    if not animes:
        return []
    return _voice_credits(animes[0] or {})


async def _rest_anime_roles(anime_id: str) -> list[dict[str, Any]]:
    """Fetch full anime role relations from Shikimori REST v1."""
    url = f"{site_url()}/api/animes/{anime_id}/roles"
    headers = {
        "User-Agent": "anime-db-bot/1.0 (https://github.com/Winbil/anime-db-bot)",
        "Accept": "application/json",
    }
    async with httpx.AsyncClient(
        timeout=20.0,
        headers=headers,
        follow_redirects=True,
    ) as client:
        response = await client.get(url)

    if response.is_error:
        preview = response.text.replace("\n", " ")[:800]
        raise RuntimeError(
            f"Shikimori roles HTTP {response.status_code} from {response.url}: {preview}"
        )

    try:
        body = response.json()
    except ValueError as exc:
        preview = response.text.replace("\n", " ")[:800]
        raise RuntimeError(
            f"Shikimori roles returned non-JSON response: {preview}"
        ) from exc

    if not isinstance(body, list):
        raise RuntimeError("Shikimori roles returned non-list JSON")
    return [item for item in body if isinstance(item, dict)]


def _rest_role_labels(entry: dict[str, Any]) -> list[str]:
    """Collect raw and localized role labels from REST serializer variants."""
    labels: list[str] = []
    for key in ("roles", "roles_russian", "rolesRussian", "roles_ru", "rolesRu"):
        value = entry.get(key)
        if isinstance(value, list):
            labels.extend(str(item) for item in value if item not in (None, ""))
        elif value not in (None, ""):
            labels.append(str(value))
    return _dedupe(labels)


def _rest_voice_stats(
    entries: list[dict[str, Any]],
) -> tuple[int, int, int, list[str]]:
    original_entries = 0
    person_entries = 0
    character_entries = 0
    all_labels: list[str] = []

    for entry in entries:
        labels = _rest_role_labels(entry)
        all_labels.extend(labels)
        if not any(_is_original_voice_role(role) for role in labels):
            continue

        original_entries += 1
        person = entry.get("person")
        character = entry.get("character")
        if isinstance(person, dict) and person:
            person_entries += 1
        if isinstance(character, dict) and character:
            character_entries += 1

    unique_labels = sorted(_dedupe(all_labels), key=str.casefold)
    return original_entries, person_entries, character_entries, unique_labels


def _rest_voice_credits(entries: list[dict[str, Any]]) -> list[PersonCredit]:
    """Extract only original Japanese seiyuu from REST role relations."""
    result: list[PersonCredit] = []
    by_person_id: dict[str, PersonCredit] = {}

    for entry in entries:
        labels = _rest_role_labels(entry)
        if not any(_is_original_voice_role(role) for role in labels):
            continue

        person = entry.get("person") or {}
        if not isinstance(person, dict) or not person:
            continue

        character = entry.get("character")
        character_name = ""
        if isinstance(character, dict):
            character_name = (
                str(character.get("russian") or "").strip()
                or str(character.get("name") or "").strip()
            )

        role = f"Озвучка: {character_name}" if character_name else "Сэйю"
        credit = _person_credit(person, [role])
        if credit is None:
            continue

        person_id = str(credit.external_ids.get("shikimori") or "").strip()
        identity = person_id or credit.name.casefold()
        existing = by_person_id.get(identity)
        if existing is None:
            by_person_id[identity] = credit
            result.append(credit)
            continue

        existing.roles = _dedupe([*existing.roles, *credit.roles])
        existing.aliases = _dedupe([*existing.aliases, *credit.aliases])

    return result


def _portrait_count(people: list[PersonCredit]) -> int:
    return sum(1 for person in people if person.portraits.get("Shikimori"))


async def _refresh_portraits(people: list[PersonCredit]) -> None:
    """Re-read person posters by stable Shikimori person ID."""
    ids = _dedupe([
        str(person.external_ids.get("shikimori") or "").strip()
        for person in people
        if str(person.external_ids.get("shikimori") or "").strip()
    ])
    if not ids:
        return

    by_id = {
        str(person.external_ids.get("shikimori") or "").strip(): person
        for person in people
        if str(person.external_ids.get("shikimori") or "").strip()
    }

    for offset in range(0, len(ids), 50):
        batch = ids[offset:offset + 50]
        data = await _graphql(PEOPLE_POSTERS_QUERY, {"ids": batch})
        for raw_person in data.get("people") or []:
            person_id = str(raw_person.get("id") or "").strip()
            credit = by_id.get(person_id)
            if credit is None:
                continue
            poster = raw_person.get("poster") or {}
            portrait = _best_poster_url(poster) if isinstance(poster, dict) else None
            if portrait:
                credit.portraits["Shikimori"] = [portrait]


async def _graphql_voice_fallback(anime_id: str) -> list[PersonCredit]:
    try:
        return await _reload_voice_credits(anime_id)
    except Exception:
        logging.warning(
            "Could not reload Shikimori GraphQL voice credits for anime %s",
            anime_id,
            exc_info=True,
        )
        return []


class ShikimoriSource(BaseShikimoriSource):
    """Shikimori metadata with REST-backed original seiyuu relations."""

    async def get_details(
        self,
        mal_id: str,
        known_ids: dict[str, str],
    ) -> AnimeRecord | None:
        record = await super().get_details(mal_id, known_ids)
        if record is None:
            return None

        anime_id = str(known_ids.get("shikimori") or record.source_id or "").strip()

        if anime_id.isdigit():
            try:
                raw_roles = await _rest_anime_roles(anime_id)
                rest_voices = _rest_voice_credits(raw_roles)
                (
                    original_entries,
                    person_entries,
                    character_entries,
                    role_labels,
                ) = _rest_voice_stats(raw_roles)

                logging.info(
                    "Shikimori REST roles for anime %s: total=%d, "
                    "original_voice_entries=%d, person_voice_entries=%d, "
                    "character_voice_entries=%d, voices=%d",
                    anime_id,
                    len(raw_roles),
                    original_entries,
                    person_entries,
                    character_entries,
                    len(rest_voices),
                )

                if not rest_voices:
                    logging.info(
                        "Shikimori REST role labels for anime %s: %s",
                        anime_id,
                        role_labels[:80],
                    )

                if rest_voices:
                    record.voices = rest_voices
                elif not record.voices:
                    record.voices = await _graphql_voice_fallback(anime_id)
            except Exception:
                logging.warning(
                    "Could not load Shikimori REST roles for anime %s",
                    anime_id,
                    exc_info=True,
                )
                if not record.voices:
                    record.voices = await _graphql_voice_fallback(anime_id)

        try:
            await _refresh_portraits(record.voices)
        except Exception:
            logging.warning(
                "Could not refresh Shikimori seiyuu portraits for anime %s",
                anime_id or "unknown",
                exc_info=True,
            )

        logging.info(
            "Shikimori people for anime %s: staff=%d (portraits=%d), "
            "voices=%d (portraits=%d)",
            anime_id or "unknown",
            len(record.staff),
            _portrait_count(record.staff),
            len(record.voices),
            _portrait_count(record.voices),
        )
        return record
