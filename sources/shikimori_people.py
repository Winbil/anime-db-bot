from __future__ import annotations

import asyncio
import copy
import logging
import os
import time
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

_REST_RATE_LOCK = asyncio.Lock()
_NEXT_REST_REQUEST_AT = 0.0
_CHARACTER_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_VOICE_CACHE: dict[str, tuple[float, list[PersonCredit]]] = {}


def _cache_ttl_seconds() -> int:
    raw = os.getenv("SHIKIMORI_PEOPLE_CACHE_TTL_SECONDS", "21600").strip()
    try:
        return max(0, int(raw))
    except ValueError:
        return 21600


def _rest_spacing_seconds() -> float:
    raw = os.getenv("SHIKIMORI_REST_MIN_INTERVAL_SECONDS", "0.24").strip()
    try:
        return max(0.20, float(raw))
    except ValueError:
        return 0.24


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


async def _rate_limited_get(
    client: httpx.AsyncClient,
    url: str,
) -> httpx.Response:
    global _NEXT_REST_REQUEST_AT

    async with _REST_RATE_LOCK:
        now = time.monotonic()
        delay = _NEXT_REST_REQUEST_AT - now
        if delay > 0:
            await asyncio.sleep(delay)
        _NEXT_REST_REQUEST_AT = time.monotonic() + _rest_spacing_seconds()

    return await client.get(url)


async def _rest_get_json(
    client: httpx.AsyncClient,
    path: str,
) -> Any:
    url = f"{site_url()}{path}"

    response: httpx.Response | None = None
    for attempt in range(3):
        response = await _rate_limited_get(client, url)
        if response.status_code != 429:
            break

        retry_after = response.headers.get("Retry-After")
        try:
            delay = max(float(retry_after or "1.2"), 1.2)
        except ValueError:
            delay = 1.2
        await asyncio.sleep(delay * (attempt + 1))

    assert response is not None
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
        "User-Agent": "anime-db-bot/1.1 (https://github.com/Winbil/anime-db-bot)",
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
    """Load characters and their original Japanese ``seyu`` lists.

    Requests are globally rate-limited across concurrent Telegram users and
    character payloads are cached, because the same popular cast is reused by
    many anime and changes very rarely.
    """
    if not character_ids:
        return []

    ttl = _cache_ttl_seconds()
    now = time.monotonic()
    result_by_id: dict[str, dict[str, Any]] = {}
    missing: list[str] = []

    for character_id in character_ids:
        cached = _CHARACTER_CACHE.get(character_id)
        if cached is not None and cached[0] > now:
            result_by_id[character_id] = copy.deepcopy(cached[1])
        else:
            if cached is not None:
                _CHARACTER_CACHE.pop(character_id, None)
            missing.append(character_id)

    if missing:
        headers = {
            "User-Agent": "anime-db-bot/1.1 (https://github.com/Winbil/anime-db-bot)",
            "Accept": "application/json",
        }
        async with httpx.AsyncClient(
            timeout=20.0,
            headers=headers,
            follow_redirects=True,
        ) as client:
            responses = await asyncio.gather(
                *(
                    _rest_get_json(client, f"/api/characters/{character_id}")
                    for character_id in missing
                ),
                return_exceptions=True,
            )

        expires_at = time.monotonic() + ttl
        for character_id, response in zip(missing, responses):
            if isinstance(response, Exception):
                logging.warning(
                    "Could not load Shikimori character %s for seiyuu lookup: %s",
                    character_id,
                    response,
                )
                continue
            if isinstance(response, dict):
                result_by_id[character_id] = response
                if ttl > 0:
                    _CHARACTER_CACHE[character_id] = (
                        expires_at,
                        copy.deepcopy(response),
                    )

    return [
        result_by_id[character_id]
        for character_id in character_ids
        if character_id in result_by_id
    ]


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
    """Compatibility helper for the startup smoke test.

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
    ttl = _cache_ttl_seconds()
    now = time.monotonic()
    cached = _VOICE_CACHE.get(anime_id)
    if cached is not None and cached[0] > now:
        logging.info("Shikimori seiyuu cache hit for anime %s", anime_id)
        return copy.deepcopy(cached[1])
    if cached is not None:
        _VOICE_CACHE.pop(anime_id, None)

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

    if ttl > 0:
        _VOICE_CACHE[anime_id] = (
            time.monotonic() + ttl,
            copy.deepcopy(voices),
        )
    return voices


class ShikimoriSource(BaseShikimoriSource):
    """Shikimori metadata with on-demand original Japanese seiyuu."""

    async def get_details(
        self,
        mal_id: str,
        known_ids: dict[str, str],
    ) -> AnimeRecord | None:
        record = await super().get_details(mal_id, known_ids)
        if record is None:
            return None

        # Character -> seyu is intentionally deferred. It can require dozens
        # of REST requests and should never delay the main anime card.
        record.voices = []
        anime_id = _clean_text(known_ids.get("shikimori") or record.source_id)
        logging.info(
            "Shikimori people for anime %s: staff=%d (portraits=%d), voices=deferred",
            anime_id or "?",
            len(record.staff),
            _portrait_count(record.staff),
        )
        return record

    async def load_voices(
        self,
        mal_id: str,
        known_ids: dict[str, str],
    ) -> list[PersonCredit]:
        """Load original Japanese seiyuu only when the Telegram UI asks for them."""
        mal_id = _clean_text(mal_id)
        anime_id = _clean_text(known_ids.get("shikimori"))
        if not mal_id.isdigit() or not anime_id.isdigit():
            return []
        return await _load_shikimori_voices(anime_id)
