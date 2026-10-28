from __future__ import annotations

import time
from typing import Any

from core.canonicalization import canonical_role_token, voice_role_token
from core.http_client import http_request
from core.identity import AnimeIdentity
from core.models import CharacterRecord, EpisodePage, EpisodeRecord, PersonCredit, TrailerRecord
from core.people_loading import PeopleBatch
from core.settings import AppSettings, SourceSettings
from core.source_errors import SourceInvalidResponse
from core.source_keys import SourceKey
from core.source_names import MAL_SOURCE_NAME
from services.rate_limits import wait_for_upstream

DEFAULT_JIKAN_API_URL = "http://127.0.0.1:8091"
JIKAN_DISPLAY_NAME = MAL_SOURCE_NAME


def _settings(settings: SourceSettings | None = None) -> SourceSettings:
    return settings or AppSettings.from_env().sources


def api_url(settings: SourceSettings | None = None) -> str:
    return _settings(settings).jikan_api_url


def _timeout(settings: SourceSettings | None = None) -> float:
    return _settings(settings).jikan_request_timeout_seconds


def _cache_ttl(
    name: str,
    settings: SourceSettings | None = None,
    default: int = 21600,
) -> float:
    settings = _settings(settings)
    if name == "JIKAN_PEOPLE_CACHE_TTL_SECONDS":
        return settings.jikan_people_cache_ttl_seconds
    if name == "JIKAN_SUPPLEMENT_CACHE_TTL_SECONDS":
        return settings.jikan_supplement_cache_ttl_seconds
    return float(default)


def _clean(value: Any) -> str:
    return " ".join(str(value or "").replace("\r", " ").split()).strip()


def _int(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _float(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for raw in values:
        value = _clean(raw)
        key = value.casefold()
        if value and key not in seen:
            seen.add(key)
            result.append(value)
    return result


def _episode(raw: dict[str, Any]) -> EpisodeRecord:
    number = _int(raw.get("number"))
    if number is None or number <= 0:
        raise ValueError("Jikan episode payload does not contain a positive episode number")
    titles = {
        key: value
        for key, raw_value in {
            "english": raw.get("title"),
            "japanese": raw.get("title_japanese"),
            "romaji": raw.get("title_romaji"),
        }.items()
        if (value := _clean(raw_value))
    }
    urls = {
        key: value
        for key, raw_value in {
            "MyAnimeList": raw.get("url"),
            "MyAnimeList forum": raw.get("forum_url"),
        }.items()
        if (value := _clean(raw_value))
    }
    return EpisodeRecord(
        number=number,
        source="mal",
        backend="jikan",
        titles=titles,
        aired_at=_clean(raw.get("aired_at")) or None,
        duration_seconds=_int(raw.get("duration_seconds")),
        score=_float(raw.get("score")),
        filler=bool(raw.get("filler")),
        recap=bool(raw.get("recap")),
        synopsis=_clean(raw.get("synopsis")) or None,
        urls=urls,
    )


def _person(raw: dict[str, Any], roles: list[str]) -> PersonCredit | None:
    name = _clean(raw.get("name"))
    if not name:
        return None
    person_id = _clean(raw.get("mal_id"))
    portrait = _clean(raw.get("image_url"))
    return PersonCredit(
        name=name,
        roles=_dedupe([canonical_role_token(role) for role in roles]),
        external_ids={"mal": person_id} if person_id else {},
        portraits={JIKAN_DISPLAY_NAME: [portrait]} if portrait else {},
    )


def _dedupe_people(values: list[PersonCredit]) -> list[PersonCredit]:
    result: dict[str, PersonCredit] = {}
    for person in values:
        key = person.external_ids.get("mal") or person.name.casefold()
        existing = result.get(key)
        if existing is None:
            result[key] = person
            continue
        existing.roles = _dedupe([*existing.roles, *person.roles])
        existing.aliases = _dedupe([*existing.aliases, *person.aliases])
        for source, urls in person.portraits.items():
            existing.portraits[source] = _dedupe([
                *existing.portraits.get(source, []),
                *urls,
            ])
    return list(result.values())


async def _get(
    path: str,
    *,
    params: dict[str, object] | None = None,
    operation: str = "episodes",
    settings: SourceSettings | None = None,
) -> dict[str, Any]:
    await wait_for_upstream("jikan", operation)
    response = await http_request(
        "jikan",
        "GET",
        f"{api_url(settings)}{path}",
        operation=operation,
        timeout=_timeout(settings),
        params=params,
    )
    try:
        body = response.json()
    except ValueError as exc:
        preview = response.text.replace("\n", " ")[:800]
        raise SourceInvalidResponse(
            f"Jikan supplement returned non-JSON response: {preview}",
            source="jikan",
            operation=operation,
        ) from exc
    if not isinstance(body, dict):
        raise SourceInvalidResponse(
            "Jikan supplement returned an unexpected JSON payload",
            source="jikan",
            operation=operation,
        )
    return body


class JikanSource:
    """MAL web supplement backed by the local on-demand Jikan parser service."""

    name = "Jikan"
    display_name = JIKAN_DISPLAY_NAME
    source_key = SourceKey.MAL
    backend_key = "jikan"

    def __init__(self, settings: SourceSettings | None = None) -> None:
        self._settings = _settings(settings)
        self._supplement_cache: dict[str, tuple[float, dict[str, Any]]] = {}
        self._people_cache: dict[str, tuple[float, dict[str, Any]]] = {}

    @staticmethod
    def _mal_id(identity: AnimeIdentity) -> str:
        value = str(identity.get("mal") or "").strip()
        return value if value.isdigit() else ""

    async def _cached_payload(
        self,
        cache: dict[str, tuple[float, dict[str, Any]]],
        mal_id: str,
        *,
        path: str,
        operation: str,
        ttl_env: str,
    ) -> dict[str, Any]:
        ttl = _cache_ttl(ttl_env, self._settings)
        now = time.monotonic()
        cached = cache.get(mal_id)
        if cached is not None and ttl > 0 and now - cached[0] < ttl:
            return cached[1]
        body = await _get(path, operation=operation, settings=self._settings)
        raw = body.get("data")
        payload = raw if isinstance(raw, dict) else {}
        if ttl > 0:
            cache[mal_id] = (now, payload)
        return payload

    async def load_metadata_supplement(self, identity: AnimeIdentity) -> dict[str, Any]:
        mal_id = self._mal_id(identity)
        if not mal_id:
            return {}
        raw = await self._cached_payload(
            self._supplement_cache,
            mal_id,
            path=f"/anime/{mal_id}/supplement",
            operation="metadata",
            ttl_env="JIKAN_SUPPLEMENT_CACHE_TTL_SECONDS",
        )
        licensors = _dedupe([value for value in raw.get("licensors") or [] if isinstance(value, str)])
        distribution: dict[int, int] = {}
        for raw_score, raw_votes in (raw.get("score_distribution") or {}).items():
            score = _int(raw_score)
            votes = _int(raw_votes)
            if score is not None and 1 <= score <= 10 and votes is not None and votes >= 0:
                distribution[score] = votes
        return {"licensors": licensors, "score_distribution": distribution}

    async def _load_people_payload(self, identity: AnimeIdentity) -> dict[str, Any]:
        mal_id = self._mal_id(identity)
        if not mal_id:
            return {}
        return await self._cached_payload(
            self._people_cache,
            mal_id,
            path=f"/anime/{mal_id}/people",
            operation="people",
            ttl_env="JIKAN_PEOPLE_CACHE_TTL_SECONDS",
        )

    async def load_characters(self, identity: AnimeIdentity) -> list[CharacterRecord]:
        raw = await self._load_people_payload(identity)
        result: list[CharacterRecord] = []
        seen: set[str] = set()
        role_map = {"main": "main", "supporting": "supporting", "background": "background"}
        for item in raw.get("characters") or []:
            if not isinstance(item, dict) or not isinstance(item.get("character"), dict):
                continue
            raw_character = item["character"]
            name = _clean(raw_character.get("name"))
            character_id = _clean(raw_character.get("mal_id"))
            if not name:
                continue
            key = character_id or name.casefold()
            if key in seen:
                continue
            seen.add(key)
            raw_role = _clean(item.get("role"))
            portrait = _clean(raw_character.get("image_url"))
            result.append(CharacterRecord(
                name=name,
                role=role_map.get(raw_role.casefold(), raw_role.casefold() or None),
                external_ids={"mal": character_id} if character_id else {},
                portraits={JIKAN_DISPLAY_NAME: [portrait]} if portrait else {},
            ))
        return result

    async def load_staff(self, identity: AnimeIdentity) -> list[PersonCredit]:
        raw = await self._load_people_payload(identity)
        people: list[PersonCredit] = []
        for item in raw.get("staff") or []:
            if not isinstance(item, dict) or not isinstance(item.get("person"), dict):
                continue
            roles = [str(value) for value in item.get("roles") or [] if _clean(value)]
            person = _person(item["person"], roles)
            if person is not None:
                people.append(person)
        return _dedupe_people(people)

    async def load_voices(self, identity: AnimeIdentity) -> list[PersonCredit]:
        raw = await self._load_people_payload(identity)
        people: list[PersonCredit] = []
        for item in raw.get("voices") or []:
            if not isinstance(item, dict) or not isinstance(item.get("person"), dict):
                continue
            character = _clean(item.get("character"))
            person = _person(item["person"], [voice_role_token(character or None)])
            if person is not None:
                people.append(person)
        return _dedupe_people(people)

    async def load_staff_batch(self, identity: AnimeIdentity, *, cursor: str | None = None, portrait_limit: int = 50) -> PeopleBatch:
        if cursor is not None:
            return PeopleBatch(complete=True)
        people = await self.load_staff(identity)
        return PeopleBatch(people=people, complete=True, total_count=len(people))

    async def load_voices_batch(self, identity: AnimeIdentity, *, cursor: str | None = None, portrait_limit: int = 50) -> PeopleBatch:
        if cursor is not None:
            return PeopleBatch(complete=True)
        people = await self.load_voices(identity)
        return PeopleBatch(people=people, complete=True, total_count=len(people))

    async def load_trailers(self, identity: AnimeIdentity) -> list[TrailerRecord]:
        mal_id = self._mal_id(identity)
        if not mal_id:
            return []
        body = await _get(
            f"/anime/{mal_id}/trailers",
            operation="trailers",
            settings=self._settings,
        )
        result: list[TrailerRecord] = []
        seen: set[str] = set()
        for raw in body.get("data") or []:
            if not isinstance(raw, dict):
                continue
            url = _clean(raw.get("url"))
            key = url.casefold()
            if not url or key in seen:
                continue
            seen.add(key)
            result.append(TrailerRecord(
                source="mal",
                backend="jikan",
                title=_clean(raw.get("title")) or None,
                kind="trailer",
                hosting="YouTube" if _clean(raw.get("youtube_id")) else None,
                url=url,
                embed_url=_clean(raw.get("embed_url")) or None,
                thumbnail=_clean(raw.get("thumbnail")) or None,
            ))
        return result

    async def load_episode_page(self, identity: AnimeIdentity, *, page: int = 1) -> EpisodePage:
        mal_id = self._mal_id(identity)
        if not mal_id:
            return EpisodePage(items=[], page=max(1, int(page)), has_next=False)
        page = max(1, int(page))
        body = await _get(
            f"/anime/{mal_id}/episodes",
            params={"page": page},
            settings=self._settings,
        )
        items = [_episode(item) for item in body.get("data") or [] if isinstance(item, dict)]
        return EpisodePage(
            items=items,
            page=page,
            last_visible_page=max(1, _int(body.get("last_visible_page")) or 1),
            has_next=bool(body.get("has_next_page")),
        )

    async def load_episode(self, identity: AnimeIdentity, episode_number: int) -> EpisodeRecord | None:
        mal_id = self._mal_id(identity)
        episode_number = int(episode_number)
        if not mal_id or episode_number <= 0:
            return None
        body = await _get(
            f"/anime/{mal_id}/episodes/{episode_number}",
            settings=self._settings,
        )
        raw = body.get("data")
        if not isinstance(raw, dict):
            return None
        return _episode(raw)
