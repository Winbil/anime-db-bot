from __future__ import annotations

import asyncio
import copy
import logging
import time
from typing import Any

from core.canonicalization import (
    VOICE_OF_PREFIX,
    normalize_key,
    person_identity_keys,
    voice_role_token,
)
from core.http_client import http_request
from core.http_config import USER_AGENT
from core.models import CharacterRecord, PersonCredit
from core.people_loading import PeopleManifest, without_portraits
from core.settings import SourceSettings, get_settings
from core.source_errors import SourceInvalidResponse
from sources.providers.shikimori_people_runtime import ShikimoriPeopleRuntime
from sources.providers.shikimori import (
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


def _settings(settings: SourceSettings | None = None) -> SourceSettings:
    return settings or get_settings().sources


def _cache_ttl_seconds(settings: SourceSettings | None = None) -> int:
    return max(0, int(_settings(settings).shikimori_people_cache_ttl_seconds))


def _rest_spacing_seconds(settings: SourceSettings | None = None) -> float:
    return max(0.20, _settings(settings).shikimori_rest_min_interval_seconds)


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).replace("\r", " ").split())


def _absolute_shikimori_url(
    value: Any, settings: SourceSettings | None = None
) -> str | None:
    url = _clean_text(value)
    if not url:
        return None
    if url.startswith("//"):
        return f"https:{url}"
    if url.startswith("/"):
        return f"{site_url(settings)}{url}"
    return url


def _best_rest_image_url(
    image: dict[str, Any], settings: SourceSettings | None = None
) -> str | None:
    for field in ("original", "x96", "preview", "x48"):
        value = _absolute_shikimori_url(image.get(field), settings)
        if value:
            return value
    return None


def _rest_person_credit(
    person: dict[str, Any],
    *,
    character_name: str,
    settings: SourceSettings | None = None,
) -> PersonCredit | None:
    name = _clean_text(person.get("name"))
    russian = _clean_text(person.get("russian"))
    names = _dedupe([name, russian])
    if not names:
        return None
    preferred = name or russian
    person_id = _clean_text(person.get("id"))
    image = person.get("image") or {}
    portrait = (
        _best_rest_image_url(image, settings) if isinstance(image, dict) else None
    )
    return PersonCredit(
        name=preferred,
        roles=[voice_role_token(character_name or None)],
        aliases=[item for item in names if item.casefold() != preferred.casefold()],
        external_ids={"shikimori": person_id} if person_id else {},
        portraits={"Shikimori": [portrait]} if portrait else {},
    )


async def _rate_limited_get(
    url: str,
    settings: SourceSettings | None = None,
):
    global _NEXT_REST_REQUEST_AT
    async with _REST_RATE_LOCK:
        now = time.monotonic()
        delay = _NEXT_REST_REQUEST_AT - now
        if delay > 0:
            await asyncio.sleep(delay)
        _NEXT_REST_REQUEST_AT = time.monotonic() + _rest_spacing_seconds(settings)
    return await http_request(
        "shikimori",
        "GET",
        url,
        operation="people",
        timeout=20.0,
        allowed_statuses={429},
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
    )


async def _rest_get_json(
    path: str,
    settings: SourceSettings | None = None,
) -> Any:
    url = f"{site_url(settings)}{path}"
    response = None
    for attempt in range(3):
        response = await _rate_limited_get(url, settings)
        if response.status_code != 429:
            break
        retry_after = response.headers.get("Retry-After")
        try:
            delay = max(float(retry_after or "1.2"), 1.2)
        except ValueError:
            delay = 1.2
        await asyncio.sleep(delay * (attempt + 1))
    assert response is not None
    if response.status_code == 429:
        # The shared transport intentionally allowed 429 through so this source's
        # legacy Retry-After policy could run first. After exhausting it, surface a
        # typed rate-limit error through the normal transport path.
        response = await http_request(
            "shikimori",
            "GET",
            url,
            operation="people",
            timeout=20.0,
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        )
    try:
        return response.json()
    except ValueError as exc:
        preview = response.text.replace("\n", " ")[:800]
        raise SourceInvalidResponse(
            f"Shikimori REST returned non-JSON response from {response.url}: {preview}",
            source="shikimori",
            operation="people",
        ) from exc


async def _rest_anime_roles(
    anime_id: str, settings: SourceSettings | None = None
) -> list[dict[str, Any]]:
    body = await _rest_get_json(f"/api/animes/{anime_id}/roles", settings)
    if not isinstance(body, list):
        raise RuntimeError("Shikimori anime roles returned non-list JSON")
    return [item for item in body if isinstance(item, dict)]


def _characters_from_roles(
    entries: list[dict[str, Any]], settings: SourceSettings | None = None
) -> list[CharacterRecord]:
    result: list[CharacterRecord] = []
    seen: set[str] = set()
    role_map = {"main": "main", "supporting": "supporting", "background": "background"}
    for entry in entries:
        character = entry.get("character")
        if not isinstance(character, dict) or not character:
            continue
        character_id = _clean_text(character.get("id"))
        name = _clean_text(character.get("name"))
        russian = _clean_text(character.get("russian"))
        preferred = name or russian
        if not preferred:
            continue
        key = character_id or preferred.casefold()
        if key in seen:
            continue
        seen.add(key)
        raw_roles = entry.get("roles") or []
        raw_role = _clean_text(
            raw_roles[0] if isinstance(raw_roles, list) and raw_roles else ""
        )
        role = role_map.get(raw_role.casefold(), raw_role.casefold() or None)
        image = character.get("image") or {}
        portrait = (
            _best_rest_image_url(image, settings) if isinstance(image, dict) else None
        )
        aliases = _dedupe([name, russian])
        result.append(
            CharacterRecord(
                name=preferred,
                role=role,
                aliases=[
                    value
                    for value in aliases
                    if value.casefold() != preferred.casefold()
                ],
                external_ids={"shikimori": character_id} if character_id else {},
                portraits={"Shikimori": [portrait]} if portrait else {},
            )
        )
    return result


async def _load_shikimori_characters(
    anime_id: str, settings: SourceSettings | None = None
) -> list[CharacterRecord]:
    roles = await _rest_anime_roles(anime_id, settings)
    return _characters_from_roles(roles, settings)


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
    settings: SourceSettings | None = None,
    runtime: ShikimoriPeopleRuntime | None = None,
) -> list[dict[str, Any]]:
    if not character_ids:
        return []
    runtime = runtime or ShikimoriPeopleRuntime()
    ttl = _cache_ttl_seconds(settings)
    result_by_id: dict[str, dict[str, Any]] = {}
    missing: list[str] = []
    for character_id in character_ids:
        cached = runtime.character_cache.get(character_id)
        if cached is not None:
            result_by_id[character_id] = copy.deepcopy(cached)
        else:
            missing.append(character_id)
    if missing:
        responses = await asyncio.gather(
            *(
                _rest_get_json(f"/api/characters/{character_id}", settings)
                for character_id in missing
            ),
            return_exceptions=True,
        )
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
                    runtime.character_cache.set(
                        character_id, copy.deepcopy(response), ttl_seconds=ttl
                    )
    return [
        result_by_id[character_id]
        for character_id in character_ids
        if character_id in result_by_id
    ]


def _voices_from_character_details(
    characters: list[dict[str, Any]], settings: SourceSettings | None = None
) -> list[PersonCredit]:
    result: list[PersonCredit] = []
    by_identity: dict[str, PersonCredit] = {}
    for character in characters:
        character_name = _clean_text(character.get("name")) or _clean_text(
            character.get("russian")
        )
        seyu = character.get("seyu") or []
        if not isinstance(seyu, list):
            continue
        for raw_person in seyu:
            if not isinstance(raw_person, dict) or not raw_person:
                continue
            credit = _rest_person_credit(
                raw_person, character_name=character_name, settings=settings
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
            portraits = _dedupe(
                [
                    *existing.portraits.get("Shikimori", []),
                    *credit.portraits.get("Shikimori", []),
                ]
            )
            if portraits:
                existing.portraits["Shikimori"] = portraits
    return result


def _rest_voice_credits(
    entries: list[dict[str, Any]], settings: SourceSettings | None = None
) -> list[PersonCredit]:
    characters: list[dict[str, Any]] = []
    for entry in entries:
        character = entry.get("character")
        person = entry.get("person")
        if (
            not isinstance(character, dict)
            or not character
            or not isinstance(person, dict)
            or not person
        ):
            continue
        converted = dict(character)
        converted["seyu"] = [person]
        characters.append(converted)
    return _voices_from_character_details(characters, settings)


def _portrait_count(people: list[PersonCredit]) -> int:
    return sum(1 for person in people if person.portraits.get("Shikimori"))


async def _refresh_people(
    people: list[PersonCredit], settings: SourceSettings | None = None
) -> None:
    ids = _dedupe(
        [
            _clean_text(person.external_ids.get("shikimori"))
            for person in people
            if _clean_text(person.external_ids.get("shikimori"))
        ]
    )
    if not ids:
        return
    by_id = {
        _clean_text(person.external_ids.get("shikimori")): person
        for person in people
        if _clean_text(person.external_ids.get("shikimori"))
    }
    for offset in range(0, len(ids), 50):
        batch = ids[offset : offset + 50]
        data = await _graphql(
            PEOPLE_DETAILS_QUERY, {"ids": batch}, settings, operation="people"
        )
        for raw_person in data.get("people") or []:
            person_id = _clean_text(raw_person.get("id"))
            credit = by_id.get(person_id)
            if credit is None:
                continue
            name = _clean_text(raw_person.get("name"))
            russian = _clean_text(raw_person.get("russian"))
            japanese = _clean_text(raw_person.get("japanese"))
            names = _dedupe([credit.name, *credit.aliases, name, russian, japanese])
            preferred = name or credit.name or russian or japanese
            if preferred:
                credit.name = preferred
                credit.aliases = [
                    item for item in names if item.casefold() != preferred.casefold()
                ]
            poster = raw_person.get("poster") or {}
            portrait = _best_poster_url(poster) if isinstance(poster, dict) else None
            if portrait:
                credit.portraits["Shikimori"] = [portrait]


async def _load_shikimori_voices(
    anime_id: str,
    settings: SourceSettings | None = None,
    runtime: ShikimoriPeopleRuntime | None = None,
) -> list[PersonCredit]:
    runtime = runtime or ShikimoriPeopleRuntime()
    ttl = _cache_ttl_seconds(settings)
    cached = runtime.voice_cache.get(anime_id)
    if cached is not None:
        logging.info("Shikimori seiyuu cache hit for anime %s", anime_id)
        return copy.deepcopy(cached)
    raw_roles = await _rest_anime_roles(anime_id, settings)
    character_ids = _character_ids_from_roles(raw_roles)
    characters = await _rest_character_details(character_ids, settings, runtime)
    voices = _voices_from_character_details(characters, settings)
    try:
        await _refresh_people(voices, settings)
    except Exception:
        logging.warning(
            "Could not refresh Shikimori seiyuu people for anime %s",
            anime_id,
            exc_info=True,
        )
    logging.info(
        "Shikimori seiyuu for anime %s: roles=%d, characters=%d/%d, voices=%d, portraits=%d",
        anime_id,
        len(raw_roles),
        len(characters),
        len(character_ids),
        len(voices),
        _portrait_count(voices),
    )
    if ttl > 0:
        runtime.voice_cache.set(anime_id, copy.deepcopy(voices), ttl_seconds=ttl)
    return voices


async def load_shikimori_voice_manifest(
    anime_id: str,
    settings: SourceSettings | None = None,
    runtime: ShikimoriPeopleRuntime | None = None,
) -> PeopleManifest:
    """Use Shikimori as voice portrait enrichment, not roster authority.

    Shikimori exposes voice actors on a character, not as an anime-specific
    person-role edge. A full character crawl can therefore include actors from
    other adaptations of the same character and inflate the anime roster. The
    exact roster is built from anime-scoped providers; Shikimori enriches that
    verified roster in bounded portrait batches.
    """
    del anime_id, settings, runtime
    return PeopleManifest(portrait_only=True)


def _voice_character_keys(people: list[PersonCredit]) -> set[str]:
    result: set[str] = set()
    for person in people:
        for role in person.roles:
            cleaned = str(role or "").strip()
            if not cleaned.startswith(VOICE_OF_PREFIX):
                continue
            key = normalize_key(cleaned.removeprefix(VOICE_OF_PREFIX))
            if key:
                result.add(key)
    return result


def _matching_character_ids(
    roles: list[dict[str, Any]],
    character_keys: set[str],
) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for entry in roles:
        raw = entry.get("character")
        if not isinstance(raw, dict) or not raw:
            continue
        names = {
            normalize_key(_clean_text(raw.get("name"))),
            normalize_key(_clean_text(raw.get("russian"))),
        }
        if not (character_keys & {name for name in names if name}):
            continue
        character_id = _clean_text(raw.get("id"))
        if character_id and character_id not in seen:
            seen.add(character_id)
            result.append(character_id)
    return result


def _merge_shikimori_candidate(
    target: PersonCredit, candidate: PersonCredit
) -> PersonCredit:
    enriched = copy.deepcopy(target)
    names = _dedupe(
        [enriched.name, *enriched.aliases, candidate.name, *candidate.aliases]
    )
    if names:
        enriched.name = names[0]
        enriched.aliases = [
            name for name in names[1:] if name.casefold() != enriched.name.casefold()
        ]
    enriched.external_ids.update(candidate.external_ids)
    for source, urls in candidate.portraits.items():
        values = _dedupe([*enriched.portraits.get(source, []), *urls])
        if values:
            enriched.portraits[source] = values
    return enriched


async def load_shikimori_voice_portraits(
    anime_id: str,
    people: list[PersonCredit],
    settings: SourceSettings | None = None,
    runtime: ShikimoriPeopleRuntime | None = None,
) -> list[PersonCredit]:
    """Match one verified voice batch to Shikimori and add its portraits."""
    anime_id = str(anime_id or "").strip()
    if not anime_id.isdigit() or not people:
        return []
    character_keys = _voice_character_keys(people)
    if not character_keys:
        return []

    runtime = runtime or ShikimoriPeopleRuntime()
    roles = await _rest_anime_roles(anime_id, settings)
    character_ids = _matching_character_ids(roles, character_keys)
    if not character_ids:
        return []
    characters = await _rest_character_details(character_ids, settings, runtime)
    candidates = _voices_from_character_details(characters, settings)

    candidate_keys = [
        (candidate, person_identity_keys([candidate.name, *candidate.aliases]))
        for candidate in candidates
    ]
    result: list[PersonCredit] = []
    for target in people:
        keys = person_identity_keys([target.name, *target.aliases])
        match = next(
            (
                candidate
                for candidate, candidate_names in candidate_keys
                if keys & candidate_names
            ),
            None,
        )
        if match is not None:
            result.append(_merge_shikimori_candidate(target, match))
    return result
