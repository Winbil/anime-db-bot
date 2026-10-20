from __future__ import annotations

import logging
from typing import Any

from core.canonicalization import is_primary_voice_role, normalize_key
from core.models import AnimeRecord, PersonCredit
from sources.shikimori import (
    ShikimoriSource as BaseShikimoriSource,
    _best_poster_url,
    _dedupe,
    _graphql,
    _person_credit,
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
    """Recognize Japanese/original voice-credit labels from Shikimori.

    The ordinary canonical matcher remains the primary rule. Extra patterns
    cover English labels that explicitly say Japanese voice while still
    excluding EN/DE/ES/etc. dub credits.
    """

    if is_primary_voice_role(value):
        return True

    key = normalize_key(value)
    if not key:
        return False

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
    result: list[PersonCredit] = []
    seen: set[tuple[str, tuple[str, ...]]] = set()

    for entry in raw.get("personRoles") or []:
        # Do not choose rolesRu OR rolesEn. Both can contain useful semantic
        # information and Shikimori may localize one more aggressively.
        all_roles = _dedupe([
            *(entry.get("rolesRu") or []),
            *(entry.get("rolesEn") or []),
        ])
        roles = [role for role in all_roles if _is_original_voice_role(role)]
        if not roles:
            continue

        credit = _person_credit(entry.get("person") or {}, roles)
        if credit is None:
            continue

        person_id = str(credit.external_ids.get("shikimori") or "").strip()
        key = (
            person_id or credit.name.casefold(),
            tuple(role.casefold() for role in credit.roles),
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


def _portrait_count(people: list[PersonCredit]) -> int:
    return sum(1 for person in people if person.portraits.get("Shikimori"))


async def _refresh_portraits(people: list[PersonCredit]) -> None:
    """Re-read person posters by stable Shikimori person ID.

    This intentionally refreshes every voice credit, even when the nested
    anime/personRoles query already returned a poster. The dedicated people
    query preloads posters and is the authoritative fallback for this UI.
    """

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


class ShikimoriSource(BaseShikimoriSource):
    """Shikimori metadata with hardened seiyuu/portrait enrichment."""

    async def get_details(
        self,
        mal_id: str,
        known_ids: dict[str, str],
    ) -> AnimeRecord | None:
        record = await super().get_details(mal_id, known_ids)
        if record is None:
            return None

        anime_id = str(known_ids.get("shikimori") or record.source_id or "").strip()

        # The base adapter normally provides voices. If it ever classifies zero
        # entries, retry from the raw role payload using rolesRu + rolesEn.
        if not record.voices and anime_id.isdigit():
            try:
                record.voices = await _reload_voice_credits(anime_id)
            except Exception:
                logging.warning(
                    "Could not reload Shikimori voice credits for anime %s",
                    anime_id,
                    exc_info=True,
                )

        try:
            await _refresh_portraits(record.voices)
        except Exception:
            # Portrait enrichment is optional and must never make the entire
            # Shikimori metadata record unavailable.
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
