from __future__ import annotations

import logging

from core.people_loading import PeopleBatch
from core.settings import SourceSettings, get_settings
from sources.providers.shikimori_people_runtime import ShikimoriPeopleRuntime
from sources.providers.shikimori_people import (
    _cache_ttl_seconds,
    _character_ids_from_roles,
    _portrait_count,
    _refresh_people,
    _rest_anime_roles,
    _rest_character_details,
    _voices_from_character_details,
)


def _settings(settings: SourceSettings | None = None) -> SourceSettings:
    return settings or get_settings().sources


def _character_chunk_size(settings: SourceSettings | None = None) -> int:
    return max(
        1,
        min(_settings(settings).shikimori_people_character_batch_size, 25),
    )


async def _character_ids_for_anime(
    anime_id: str,
    settings: SourceSettings | None = None,
    runtime: ShikimoriPeopleRuntime | None = None,
) -> list[str]:
    runtime = runtime or ShikimoriPeopleRuntime()
    cached = runtime.role_index_cache.get(anime_id)
    if cached is not None:
        return list(cached)

    raw_roles = (
        await _rest_anime_roles(anime_id)
        if settings is None
        else await _rest_anime_roles(anime_id, settings)
    )
    character_ids = _character_ids_from_roles(raw_roles)
    ttl = _cache_ttl_seconds(settings)
    if ttl > 0:
        runtime.role_index_cache.set(anime_id, list(character_ids), ttl_seconds=ttl)
    return character_ids


async def load_shikimori_voices_batch(
    anime_id: str,
    *,
    cursor: str | None = None,
    portrait_limit: int = 50,
    settings: SourceSettings | None = None,
    runtime: ShikimoriPeopleRuntime | None = None,
) -> PeopleBatch:
    """Load one bounded Shikimori seiyuu batch.

    The cursor is an index into the anime's character list.  We keep scanning
    characters until the current batch contains roughly ``portrait_limit``
    unique seiyuu with portraits.  Characters that yield only names/no portrait
    do not consume that budget, matching the Telegram pagination semantics.

    Character requests are still cached by ``shikimori_people``.  A small
    character chunk is used so one API round does not overshoot the portrait
    budget by a large amount while avoiding a new HTTP client per character.
    """
    anime_id = str(anime_id or "").strip()
    if not anime_id.isdigit():
        return PeopleBatch(complete=True)

    portrait_limit = max(1, int(portrait_limit))
    try:
        index = max(0, int(cursor or "0"))
    except ValueError:
        index = 0

    runtime = runtime or ShikimoriPeopleRuntime()
    character_ids = await _character_ids_for_anime(
        anime_id,
        settings,
        runtime,
    )
    if index >= len(character_ids):
        return PeopleBatch(complete=True)

    chunk_size = _character_chunk_size(settings)
    characters: list[dict] = []
    people = []

    while index < len(character_ids):
        batch_ids = character_ids[index : index + chunk_size]
        if not batch_ids:
            break
        details = await _rest_character_details(batch_ids, settings, runtime)
        characters.extend(details)
        index += len(batch_ids)
        people = _voices_from_character_details(characters, settings)
        if _portrait_count(people) >= portrait_limit:
            break

    try:
        if settings is None:
            await _refresh_people(people)
        else:
            await _refresh_people(people, settings)
    except Exception:
        logging.warning(
            "Could not refresh progressive Shikimori seiyuu batch for anime %s",
            anime_id,
            exc_info=True,
        )

    complete = index >= len(character_ids)
    logging.info(
        "Progressive Shikimori seiyuu batch for anime %s: characters=%d/%d, "
        "voices=%d, portraits=%d, complete=%s",
        anime_id,
        index,
        len(character_ids),
        len(people),
        _portrait_count(people),
        complete,
    )
    return PeopleBatch(
        people=people,
        next_cursor=None if complete else str(index),
        complete=complete,
        total_count=None,
    )
