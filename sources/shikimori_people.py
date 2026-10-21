from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from core.models import AnimeRecord, PersonCredit
from sources.shikimori import (
    ShikimoriSource as BaseShikimoriSource,
    _best_poster_url,
    _dedupe,
    _graphql,
    site_url,
)


PEOPLE_DETAILS_QUERY = """
query PeopleDetails($ids: [ID!]) {
  people(ids: $ids, limit: 50) {
    id
    name
    russian
    japanese
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


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).replace("\r", " ").split())


def _absolute_shikimori_url(value: Any) -> str | None:
    url = _clean_text(value)
    if not url:
        return None
    if url.startswith("//"):
        return f"https:{url}"
    if url.startswith("/"):
        return f"{site_url()}{url}"
    return url


def _best_rest_image_url(image: dict[str, Any]) -> str | None:
    for field in ("original", "x96", "preview", "x48"):
        value = _absolute_shikimori_url(image.get(field))
        if value:
            return value
    return None


def _rest_person_credit(
    person: dict[str, Any],
    *,
    character_name: str,
) -> PersonCredit | None:
    russian = _clean_text(person.get("russian"))
    name = _clean_text(person.get("name"))
    names = _dedupe([russian, name])
    if not names:
        return None

    preferred = russian or name
    person_id = _clean_text(person.get("id"))
    image = person.get("image") or {}
    portrait = _best_rest_image_url(image) if isinstance(image, dict) else None
    role = f"Озвучка: {character_name}" if character_name else "Сэйю"

    return PersonCredit(
        name=preferred,
        roles=[role],
        aliases=[item for item in names if item.casefold() != preferred.casefold()],
        external_ids={"shikimori": person_id} if person_id else {},
        portraits={"Shikimori": [portrait]} if portrait else {},
    )


async def _rest_get_json(
    client: httpx.AsyncClient,
    path: str,
) -> Any:
    url = f"{site_url()}{path}"
    response = await client.get(url)

    if response.status_code == 429:
        retry_after = response.headers.get("Retry-After")
        try:
            delay = max(float(retry_after or "1.2"), 1.2)
        except ValueError:
            delay = 1.2
        await asyncio.sleep(delay)
        response = await client.get(url)

    if response.is_error:
        preview = response.text.replace("\n", " ")[:800]
        raise RuntimeError(
            f"Shikimori REST HTTP {response.status_code} from {response.url}: {preview}"
        )

    try:
        return response.json()
    except ValueError as exc:
        preview = response.text.replace("\n", " ")[:800]
        raise RuntimeError(
            f"Shikimori REST returned non-JSON response from {response.url}: {preview}"
        ) from exc


async def _rest_anime_roles(anime_id: str) -> list[dict[str, Any]]:
    headers = {
        "User-Agent": "anime-db-bot/1.0 (https://github.com/Winbil/anime-db-bot)",
        "Accept": "application/json",
    }
    async with httpx.AsyncClient(
        timeout=20.0,
        headers=headers,
        follow_redirects=True,
    ) as client:
        body = await _rest_get_json(client, f"/api/animes/{anime_id}/roles")

    if not isinstance(body, list):
        raise RuntimeError("Shikimori anime roles returned non-list JSON")
    return [item for item in body if isinstance(item, dict)]


def _character_ids_from_roles(entries: list[dict[str, Any]]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()

    for entry in entries:
        character = entry.get("character")
        if not isinstance(character, dict) or not character:
            continue
        character_id = _clean_text(character.get("id"))
        if not character_id or character_id in seen:
            continue
        seen.add(character_id)
        result.append(character_id)

    return result


async def _rest_character_details(
    character_ids: list[str],
) -> list[dict[str, Any]]:
    """Load characters and their original Japanese `seyu` lists.

    `/api/animes/:id/roles` contains character rows and staff rows separately;
    it does not contain a person↔character voice link. Shikimori exposes that
    relation on `/api/characters/:id` through the `seyu` field instead.
    """
    if not character_ids:
        return []

    headers = {
        "User-Agent": "anime-db-bot/1.0 (https://github.com/Winbil/anime-db-bot)",
        "Accept": "application/json",
    }
    result: list[dict[str, Any]] = []

    async with httpx.AsyncClient(
        timeout=20.0,
        headers=headers,
        follow_redirects=True,
    ) as client:
        # Shikimori allows 5 rps. Use four requests per batch so the anime
        # roles request/other metadata traffic still has headroom.
        for offset in range(0, len(character_ids), 4):
            batch = character_ids[offset:offset + 4]
            responses = await asyncio.gather(
                *(
                    _rest_get_json(client, f"/api/characters/{character_id}")
                    for character_id in batch
                ),
                return_exceptions=True,
            )

            for character_id, response in zip(batch, responses):
                if isinstance(response, Exception):
                    logging.warning(
                        "Could not load Shikimori character %s for seiyuu lookup: %s",
                        character_id,
                        response,
                    )
                    continue
                if isinstance(response, dict):
                    result.append(response)

            if offset + 4 < len(character_ids):
                await asyncio.sleep(1.05)

    return result


def _voices_from_character_details(
    characters: list[dict[str, Any]],
) -> list[PersonCredit]:
    result: list[PersonCredit] = []
    by_identity: dict[str, PersonCredit] = {}

    for character in characters:
        character_name = (
            _clean_text(character.get("russian"))
            or _clean_text(character.get("name"))
        )

        seyu = character.get("seyu") or []
        if not isinstance(seyu, list):
            continue

        for raw_person in seyu:
            if not isinstance(raw_person, dict) or not raw_person:
                continue

            credit = _rest_person_credit(
                raw_person,
                character_name=character_name,
            )
            if credit is None:
                continue

            person_id = _clean_text(credit.external_ids.get("shikimori"))
            identity = person_id or credit.name.casefold()
            existing = by_identity.get(identity)
            if existing is None:
                by_identity[identity] = credit
                result.append(credit)
                continue

            existing.roles = _dedupe([*existing.roles, *credit.roles])
            existing.aliases = _dedupe([*existing.aliases, *credit.aliases])
            portraits = _dedupe([
                *existing.portraits.get("Shikimori", []),
                *credit.portraits.get("Shikimori", []),
            ])
            if portraits:
                existing.portraits["Shikimori"] = portraits

    return result


def _rest_voice_credits(entries: list[dict[str, Any]]) -> list[PersonCredit]:
    """Compatibility helper for the existing startup smoke test.

    Real Shikimori anime-role rows do not contain person and character in the
    same row. This helper converts synthetic paired rows into the same
    character.seyu representation used by the real parser.
    """
    characters: list[dict[str, Any]] = []
    for entry in entries:
        character = entry.get("character")
        person = entry.get("person")
        if not isinstance(character, dict) or not character:
            continue
        if not isinstance(person, dict) or not person:
            continue
        converted = dict(character)
        converted["seyu"] = [person]
        characters.append(converted)
    return _voices_from_character_details(characters)


def _portrait_count(people: list[PersonCredit]) -> int:
    return sum(1 for person in people if person.portraits.get("Shikimori"))


async def _refresh_people(people: list[PersonCredit]) -> None:
    """Upgrade REST seiyuu with Japanese aliases and the best poster URL."""
    ids = _dedupe([
        _clean_text(person.external_ids.get("shikimori"))
        for person in people
        if _clean_text(person.external_ids.get("shikimori"))
    ])
    if not ids:
        return

    by_id = {
        _clean_text(person.external_ids.get("shikimori")): person
        for person in people
        if _clean_text(person.external_ids.get("shikimori"))
    }

    for offset in range(0, len(ids), 50):
        batch = ids[offset:offset + 50]
        data = await _graphql(PEOPLE_DETAILS_QUERY, {"ids": batch})

        for raw_person in data.get("people") or []:
            person_id = _clean_text(raw_person.get("id"))
            credit = by_id.get(person_id)
            if credit is None:
                continue

            russian = _clean_text(raw_person.get("russian"))
            name = _clean_text(raw_person.get("name"))
            japanese = _clean_text(raw_person.get("japanese"))
            names = _dedupe([credit.name, *credit.aliases, russian, name, japanese])
            preferred = russian or credit.name or name or japanese
            if preferred:
                credit.name = preferred
                credit.aliases = [
                    item
                    for item in names
                    if item.casefold() != preferred.casefold()
                ]

            poster = raw_person.get("poster") or {}
            portrait = _best_poster_url(poster) if isinstance(poster, dict) else None
            if portrait:
                credit.portraits["Shikimori"] = [portrait]


async def _load_shikimori_voices(anime_id: str) -> list[PersonCredit]:
    raw_roles = await _rest_anime_roles(anime_id)
    character_ids = _character_ids_from_roles(raw_roles)
    characters = await _rest_character_details(character_ids)
    voices = _voices_from_character_details(characters)

    try:
        await _refresh_people(voices)
    except Exception:
        logging.warning(
            "Could not refresh Shikimori seiyuu people for anime %s",
            anime_id,
            exc_info=True,
        )

    logging.info(
        "Shikimori seiyuu for anime %s: roles=%d, characters=%d/%d, "
        "voices=%d, portraits=%d",
        anime_id,
        len(raw_roles),
        len(characters),
        len(character_ids),
        len(voices),
        _portrait_count(voices),
    )
    return voices


class ShikimoriSource(BaseShikimoriSource):
    """Shikimori metadata with character-backed original Japanese seiyuu."""

    async def get_details(
        self,
        mal_id: str,
        known_ids: dict[str, str],
    ) -> AnimeRecord | None:
        record = await super().get_details(mal_id, known_ids)
        if record is None:
            return None

        anime_id = _clean_text(known_ids.get("shikimori") or record.source_id)
        if not anime_id.isdigit():
            return record

        try:
            voices = await _load_shikimori_voices(anime_id)
            if voices:
                record.voices = voices
        except Exception:
            # Seiyuu portraits are enrichment. Do not make all Shikimori
            # metadata unavailable if character details fail temporarily.
            logging.warning(
                "Could not load Shikimori character-backed seiyuu for anime %s",
                anime_id,
                exc_info=True,
            )

        logging.info(
            "Shikimori people for anime %s: staff=%d (portraits=%d), "
            "voices=%d (portraits=%d)",
            anime_id,
            len(record.staff),
            _portrait_count(record.staff),
            len(record.voices),
            _portrait_count(record.voices),
        )
        return record
