from __future__ import annotations

import asyncio
import html
import math
import re
import time
from typing import Any

from core.cache import BoundedTTLCache
from core.canonicalization import (
    canonical_genre_token,
    canonical_role_token,
    voice_role_token,
)
from core.http_client import http_request
from core.identity import AnimeIdentity
from core.models import (
    AnimeRecord,
    CharacterRecord,
    DescriptionDetails,
    EpisodePage,
    EpisodeRecord,
    PersonCredit,
    PopularityStats,
)
from core.people_loading import PeopleManifest, without_portraits
from core.settings import SourceSettings, get_settings
from core.source_errors import SourceInvalidResponse, SourceUnavailable
from core.source_keys import SourceKey
from core.temporal import parse_partial_date
from localization import source_value_key
from services.runtime.rate_limits import wait_for_upstream

ANISEARCH_SOURCE_NAME = "AniSearch"
DEFAULT_API_URL = "https://api.anisearch.com"
SUPPORTED_LOCALIZATIONS = ("en", "ja", "de", "es", "fr", "it")
_LOCALIZED_TITLE_KEYS = {
    "en": "english",
    "ja": "japanese",
    "de": "german",
    "es": "spanish",
    "fr": "french",
    "it": "italian",
}
_EPISODE_LOCALIZATIONS = ("ja", "en", "de", "es", "fr", "it")
_PAGE_SIZE = 100

# The read-only Database API does not require OAuth. Keep its documented
# 10-second pacing separate from the coarse per-minute safety limiter used by
# the rest of the application. App ID/App Secret are OAuth application
# credentials for future user-authorized features and are never sent here.
_NETWORK_LOCK = asyncio.Lock()
_LAST_NETWORK_REQUEST_AT = 0.0
_MAX_INTERACTIVE_PACE_WAIT_SECONDS = 0.75

_FULL_CACHE: BoundedTTLCache[tuple[str, str], dict[str, Any]] = BoundedTTLCache(
    max_entries=750,
    name="anisearch_full",
)
_INFLIGHT_LOCK = asyncio.Lock()
_INFLIGHT: dict[tuple[str, str, str], asyncio.Task[dict[str, Any] | None]] = {}


def _settings(settings: SourceSettings | None = None) -> SourceSettings:
    return settings or get_settings().sources


def _api_url(settings: SourceSettings | None = None) -> str:
    return (_settings(settings).anisearch_api_url or DEFAULT_API_URL).rstrip("/")


def _timeout(settings: SourceSettings | None = None) -> float:
    return max(3.0, float(_settings(settings).anisearch_request_timeout_seconds))


def _cache_ttl(settings: SourceSettings | None = None) -> float:
    return max(0.0, float(_settings(settings).anisearch_cache_ttl_seconds))


def _clean(value: Any) -> str:
    return " ".join(str(value or "").replace("\r", " ").split()).strip()


def _clean_multiline(value: Any) -> str:
    raw = str(value or "")
    if not raw.strip():
        return ""
    raw = re.sub(r"<br\s*/?>", "\n", raw, flags=re.IGNORECASE)
    raw = re.sub(r"<[^>]+>", "", raw)
    raw = html.unescape(raw)
    lines = [" ".join(line.split()) for line in raw.splitlines()]
    return "\n".join(line for line in lines if line).strip()


def _int(value: Any) -> int | None:
    try:
        return int(value) if value is not None and str(value).strip() else None
    except (TypeError, ValueError):
        return None


def _float(value: Any) -> float | None:
    try:
        return float(value) if value is not None and str(value).strip() else None
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


def _anisearch_id(identity: AnimeIdentity) -> str:
    value = _clean(identity.get(SourceKey.ANISEARCH))
    return value if value.isdigit() and int(value) > 0 else ""


def _release(raw: dict[str, Any], language: str) -> dict[str, Any]:
    releases = raw.get("releases") or {}
    value = releases.get(language) if isinstance(releases, dict) else None
    return value if isinstance(value, dict) else {}


def _titles(raw: dict[str, Any]) -> tuple[dict[str, str], list[str]]:
    titles: dict[str, str] = {}
    synonyms: list[str] = []

    main = _clean(raw.get("title"))
    native = _clean(raw.get("title_native"))
    if main:
        titles["romaji"] = main
    if native:
        titles["japanese"] = native

    synonyms.extend(_clean(item) for item in raw.get("synonyms") or [])
    for language in SUPPORTED_LOCALIZATIONS:
        release = _release(raw, language)
        synonyms.extend(_clean(item) for item in release.get("synonyms") or [])
        localized = _clean(release.get("title"))
        title_key = _LOCALIZED_TITLE_KEYS[language]
        if localized and not (language == "ja" and native):
            titles[title_key] = localized
        if localized:
            synonyms.append(localized)

    chosen = {value.casefold() for value in titles.values() if value}
    return titles, [
        value for value in _dedupe(synonyms) if value.casefold() not in chosen
    ]


def _external_ids(raw: dict[str, Any], anisearch_id: str) -> dict[str, str]:
    result = {"anisearch": anisearch_id}
    external = raw.get("external_ids") or {}
    if isinstance(external, dict):
        mapping = {"myanimelist": "mal", "anidb": "anidb"}
        for upstream, local in mapping.items():
            value = _clean(external.get(upstream))
            if value:
                result[local] = value
    return result


def _season(raw: dict[str, Any]) -> tuple[str | None, int | None]:
    value = _clean(raw.get("season"))
    year = _int(raw.get("year"))
    if value:
        parts = value.split()
        season_raw = parts[0]
        season = source_value_key(
            "anisearch", "season", season_raw, default=season_raw.casefold()
        )
        if year is None and len(parts) > 1 and parts[-1].isdigit():
            year = int(parts[-1])
        return season, year
    return None, year


def _score(value: Any) -> float | None:
    raw = _float(value)
    if raw is None:
        return None
    return round(max(0.0, min(100.0, raw)) / 10.0, 2)


def _genres(raw: dict[str, Any]) -> list[str]:
    value = raw.get("genres") or {}
    if not isinstance(value, dict):
        return []
    combined: list[str] = []
    combined.extend(_clean(item) for item in value.get("main") or [])
    combined.extend(_clean(item) for item in value.get("subsidiary") or [])
    return _dedupe([canonical_genre_token(item) for item in combined if item])


def _source_materials(raw: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for item in raw.get("adapted_from") or []:
        value = _clean(item)
        if not value:
            continue
        mapped = source_value_key("anisearch", "source", value, default=value)
        if mapped:
            values.append(mapped)
    return _dedupe(values)


def _studios(raw: dict[str, Any]) -> list[str]:
    result: list[str] = []
    for item in raw.get("studios") or []:
        if isinstance(item, dict):
            result.append(_clean(item.get("name")))
    return _dedupe(result)


def _licensors(raw: dict[str, Any]) -> list[str]:
    # Non-Japanese release publishers are localization/distribution licensors.
    # Keep Japanese publishers out of this field because they usually describe
    # original domestic distribution rather than a localization license.
    result: list[str] = []
    for language in SUPPORTED_LOCALIZATIONS:
        if language == "ja":
            continue
        for item in _release(raw, language).get("publishers") or []:
            if isinstance(item, dict):
                result.append(_clean(item.get("name")))
    return _dedupe(result)


def _poster(raw: dict[str, Any]) -> str | None:
    cover = raw.get("cover") or {}
    if not isinstance(cover, dict) or cover.get("available") is False:
        return None
    return _clean(cover.get("large")) or _clean(cover.get("medium")) or None


def _rating(raw: dict[str, Any]) -> str | None:
    cover = raw.get("cover") or {}
    nsfw = _int(cover.get("nsfw")) if isinstance(cover, dict) else None
    return "adult" if nsfw == 18 else None


def _record(raw: dict[str, Any], anisearch_id: str) -> AnimeRecord:
    titles, synonyms = _titles(raw)
    season, season_year = _season(raw)
    poster = _poster(raw)
    url = _clean(raw.get("url"))
    return AnimeRecord(
        source=ANISEARCH_SOURCE_NAME,
        source_id=anisearch_id,
        titles=titles,
        synonyms=synonyms,
        external_ids=_external_ids(raw, anisearch_id),
        kind=source_value_key("anisearch", "type", raw.get("type")),
        status=source_value_key("anisearch", "status", raw.get("status")),
        rating=_rating(raw),
        season=season,
        season_year=season_year,
        episodes_total=_int(raw.get("episodes")),
        duration_minutes=_int(raw.get("duration")),
        aired_on=parse_partial_date(raw.get("aired_from")),
        released_on=parse_partial_date(raw.get("aired_to")),
        score=_score(raw.get("score")),
        genres=_genres(raw),
        studios=_studios(raw),
        licensors=_licensors(raw),
        source_materials=_source_materials(raw),
        posters=[poster] if poster else [],
        urls={"AniSearch": url} if url else {},
    )


def _character_role(value: Any) -> str | None:
    raw = _clean(value).casefold()
    mapping = {
        "main": "main",
        "supporting": "supporting",
        "background": "background",
        "cameo": "background",
    }
    return mapping.get(raw, raw or None)


def _characters(raw: dict[str, Any]) -> list[CharacterRecord]:
    details = raw.get("details") or {}
    values = details.get("characters") if isinstance(details, dict) else None
    result: list[CharacterRecord] = []
    seen: set[str] = set()
    for item in values or []:
        if not isinstance(item, dict):
            continue
        name = _clean(item.get("name"))
        source_id = _clean(item.get("id"))
        if not name:
            continue
        key = source_id or name.casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(
            CharacterRecord(
                name=name,
                role=_character_role(item.get("role")),
                external_ids={"anisearch": source_id} if source_id else {},
            )
        )
    return result


def _staff(raw: dict[str, Any]) -> list[PersonCredit]:
    details = raw.get("details") or {}
    groups = details.get("staff") if isinstance(details, dict) else None
    merged: dict[str, PersonCredit] = {}
    for group in groups or []:
        if not isinstance(group, dict):
            continue
        group_name = _clean(group.get("name"))
        for creator in group.get("creators") or []:
            if not isinstance(creator, dict):
                continue
            name = _clean(creator.get("name"))
            source_id = _clean(creator.get("id"))
            if not name:
                continue
            roles: list[str] = []
            for task in creator.get("tasks") or []:
                if not isinstance(task, dict):
                    continue
                # AniSearch exposes exhaustive per-episode production credits.
                # The global people section represents series-level staff; keeping
                # episode-scoped work here can add hundreds of portraitless entries
                # and belongs in a future episode-staff view instead.
                if _clean(task.get("episodes")):
                    continue
                task_name = _clean(task.get("name")) or group_name
                if task_name:
                    roles.append(canonical_role_token(task_name))
            roles = _dedupe(roles)
            if not roles:
                continue
            key = source_id or name.casefold()
            existing = merged.get(key)
            if existing is None:
                merged[key] = PersonCredit(
                    name=name,
                    roles=roles,
                    external_ids={"anisearch": source_id} if source_id else {},
                )
            else:
                existing.roles = _dedupe([*existing.roles, *roles])
    return list(merged.values())


def _voices(raw: dict[str, Any]) -> list[PersonCredit]:
    details = raw.get("details") or {}
    characters = details.get("characters") if isinstance(details, dict) else None
    merged: dict[str, PersonCredit] = {}
    for character in characters or []:
        if not isinstance(character, dict):
            continue
        character_name = _clean(character.get("name"))
        voices = character.get("voices") or {}
        if not isinstance(voices, dict):
            continue
        for language in SUPPORTED_LOCALIZATIONS:
            # Japanese credits remain the untagged original-language baseline.
            # Every localized dub keeps an explicit language suffix so the
            # combined roster never disguises a dub actor as a Japanese seiyuu.
            for voice in voices.get(language) or []:
                if not isinstance(voice, dict):
                    continue
                person = voice.get("person")
                if not isinstance(person, dict):
                    continue
                name = _clean(person.get("name"))
                source_id = _clean(person.get("id"))
                if not name:
                    continue
                role_character = character_name or _clean(voice.get("name"))
                if language != "ja" and role_character:
                    role_character = f"{role_character} [{language.upper()}]"
                role = voice_role_token(role_character or None)
                key = source_id or name.casefold()
                existing = merged.get(key)
                if existing is None:
                    merged[key] = PersonCredit(
                        name=name,
                        roles=[role],
                        external_ids={"anisearch": source_id} if source_id else {},
                    )
                elif role not in existing.roles:
                    existing.roles.append(role)
    return list(merged.values())


def _episode_number(value: Any) -> int | None:
    raw = _clean(value)
    return int(raw) if raw.isdigit() and int(raw) > 0 else None


def _episodes(raw: dict[str, Any]) -> list[EpisodeRecord]:
    details = raw.get("details") or {}
    by_language = details.get("episodes") if isinstance(details, dict) else None
    if not isinstance(by_language, dict):
        return []

    merged: dict[int, EpisodeRecord] = {}
    # Japanese is the original-language baseline. Localized rows add translated
    # titles without replacing publication metadata already supplied by an
    # earlier/original row.
    for language in _EPISODE_LOCALIZATIONS:
        for item in by_language.get(language) or []:
            if not isinstance(item, dict):
                continue
            number = _episode_number(item.get("number"))
            if number is None:
                continue
            record = merged.get(number)
            if record is None:
                record = EpisodeRecord(
                    number=number,
                    source="anisearch",
                    backend="anisearch",
                )
                merged[number] = record
            title = _clean(item.get("title"))
            if title:
                record.titles[_LOCALIZED_TITLE_KEYS[language]] = title
            if record.duration_seconds is None:
                minutes = _int(item.get("minutes"))
                if minutes and minutes > 0:
                    record.duration_seconds = minutes * 60
            if record.aired_at is None:
                record.aired_at = parse_partial_date(item.get("publication"))
            record.filler = record.filler or bool(item.get("filler"))
            record.recap = record.recap or bool(item.get("recap"))

    return [merged[number] for number in sorted(merged)]


def _description(raw: dict[str, Any]) -> DescriptionDetails:
    url = _clean(raw.get("url"))
    localized: dict[str, str] = {}
    for language in SUPPORTED_LOCALIZATIONS:
        synopsis = _release(raw, language).get("synopsis")
        if not isinstance(synopsis, dict):
            continue
        value = _clean_multiline(synopsis.get("text"))
        if not value:
            continue
        if _clean(synopsis.get("source")).casefold() == "anisearch" and url:
            value = f"{value}\n\naniSearch: {url}"
        localized[language] = value

    fallback = localized.get("en") or localized.get("ja")
    if fallback is None and localized:
        fallback = next(iter(localized.values()))
    return DescriptionDetails(
        description=fallback,
        localized_descriptions=localized,
    )


def _popularity(raw: dict[str, Any]) -> PopularityStats:
    return PopularityStats(
        rank=_int(raw.get("rank")),
        list_users=_int(raw.get("member_count")),
        scoring_users=_int(raw.get("rating_count")),
    )


async def _paced_request(
    path: str,
    *,
    operation: str,
    settings: SourceSettings,
) -> dict[str, Any]:
    global _LAST_NETWORK_REQUEST_AT

    min_interval = 10.1

    if _NETWORK_LOCK.locked():
        raise SourceUnavailable(
            "AniSearch request already in flight; skipping this interactive call",
            source="anisearch",
            operation=operation,
            transient=False,
        )

    async with _NETWORK_LOCK:
        wait_for = _LAST_NETWORK_REQUEST_AT + min_interval - time.monotonic()
        if wait_for > _MAX_INTERACTIVE_PACE_WAIT_SECONDS:
            raise SourceUnavailable(
                "AniSearch pacing window is still active; skipping this interactive call",
                source="anisearch",
                operation=operation,
                transient=False,
                retry_after=wait_for,
            )
        if wait_for > 0:
            await asyncio.sleep(wait_for)
        try:
            response = await http_request(
                "anisearch",
                "GET",
                f"{_api_url(settings)}{path}",
                operation=operation,
                timeout=_timeout(settings),
            )
        finally:
            # Failed requests count against the documented aniSearch allowance too.
            _LAST_NETWORK_REQUEST_AT = time.monotonic()

    try:
        payload = response.json()
    except ValueError as exc:
        raise SourceInvalidResponse(
            "AniSearch returned invalid JSON",
            source="anisearch",
            operation=operation,
        ) from exc
    if not isinstance(payload, dict):
        raise SourceInvalidResponse(
            "AniSearch returned a non-object payload",
            source="anisearch",
            operation=operation,
        )
    return payload


async def _fetch_item(
    anisearch_id: str,
    *,
    settings: SourceSettings,
) -> dict[str, Any] | None:
    payload = await _paced_request(
        f"/v1/anime/{anisearch_id}/full",
        operation="full",
        settings=settings,
    )
    values = payload.get("results")
    if not isinstance(values, list):
        raise SourceInvalidResponse(
            "AniSearch payload is missing results[]",
            source="anisearch",
            operation="full",
        )
    item = next(
        (
            value
            for value in values
            if isinstance(value, dict) and str(value.get("id") or "") == anisearch_id
        ),
        None,
    )
    if item is None:
        return None
    ttl = _cache_ttl(settings)
    if ttl > 0:
        _FULL_CACHE.set(
            (_api_url(settings), anisearch_id),
            item,
            ttl_seconds=ttl,
        )
    return item


async def _load_item(
    anisearch_id: str,
    *,
    settings: SourceSettings,
) -> dict[str, Any] | None:
    cache_key = (_api_url(settings), anisearch_id)
    cached = _FULL_CACHE.get(cache_key)
    if cached is not None:
        return cached

    task_key = (_api_url(settings), anisearch_id, "full")
    async with _INFLIGHT_LOCK:
        task = _INFLIGHT.get(task_key)
        if task is None:
            task = asyncio.create_task(_fetch_item(anisearch_id, settings=settings))
            _INFLIGHT[task_key] = task
    try:
        return await task
    finally:
        async with _INFLIGHT_LOCK:
            if _INFLIGHT.get(task_key) is task:
                _INFLIGHT.pop(task_key, None)


class AniSearchSource:
    """Identity-native aniSearch Database API adapter.

    The public API exposes no query-search endpoint. Search remains handled by the
    existing providers; confirmed ``anisearch`` IDs arrive through the local mapping
    graph and are then used for metadata and lazy sections.
    """

    name = ANISEARCH_SOURCE_NAME
    display_name = ANISEARCH_SOURCE_NAME
    source_key = SourceKey.ANISEARCH
    backend_key = "anisearch"

    def __init__(self, settings: SourceSettings | None = None) -> None:
        self._settings = _settings(settings)

    async def _payload(self, identity: AnimeIdentity) -> dict[str, Any] | None:
        source_id = _anisearch_id(identity)
        if not source_id:
            return None
        return await _load_item(source_id, settings=self._settings)

    async def get_details(self, identity: AnimeIdentity) -> AnimeRecord | None:
        # AniSearch places id/full and the individual heavy endpoints in the same
        # 10-second public throttle group. Fetching one cached /full payload here
        # avoids a mandatory 10-second wait before people/episodes while the
        # normalized main record still excludes those heavy sections.
        raw = await self._payload(identity)
        source_id = _anisearch_id(identity)
        return _record(raw, source_id) if raw is not None and source_id else None

    async def load_popularity(self, identity: AnimeIdentity) -> PopularityStats:
        raw = await self._payload(identity)
        return _popularity(raw) if raw is not None else PopularityStats()

    async def load_description(self, identity: AnimeIdentity) -> DescriptionDetails:
        raw = await self._payload(identity)
        return _description(raw) if raw is not None else DescriptionDetails()

    async def load_characters(self, identity: AnimeIdentity) -> list[CharacterRecord]:
        raw = await self._payload(identity)
        return _characters(raw) if raw is not None else []

    async def load_staff(self, identity: AnimeIdentity) -> list[PersonCredit]:
        raw = await self._payload(identity)
        return _staff(raw) if raw is not None else []

    async def load_voices(self, identity: AnimeIdentity) -> list[PersonCredit]:
        raw = await self._payload(identity)
        return _voices(raw) if raw is not None else []

    async def load_staff_manifest(self, identity: AnimeIdentity) -> PeopleManifest:
        values = await self.load_staff(identity)
        return PeopleManifest(people=without_portraits(values))

    async def load_voices_manifest(self, identity: AnimeIdentity) -> PeopleManifest:
        values = await self.load_voices(identity)
        return PeopleManifest(people=without_portraits(values))

    async def load_episode_page(
        self,
        identity: AnimeIdentity,
        *,
        page: int = 1,
    ) -> EpisodePage:
        await wait_for_upstream("anisearch", "episodes")
        raw = await self._payload(identity)
        page = max(1, int(page))
        if raw is None:
            return EpisodePage(items=[], page=page, has_next=False)
        values = _episodes(raw)
        start = (page - 1) * _PAGE_SIZE
        items = values[start : start + _PAGE_SIZE]
        last_page = max(1, math.ceil(len(values) / _PAGE_SIZE))
        return EpisodePage(
            items=items,
            page=page,
            last_visible_page=last_page,
            has_next=page < last_page,
        )

    async def load_episode(
        self,
        identity: AnimeIdentity,
        episode_number: int,
    ) -> EpisodeRecord | None:
        await wait_for_upstream("anisearch", "episodes")
        raw = await self._payload(identity)
        if raw is None:
            return None
        wanted = int(episode_number)
        return next((item for item in _episodes(raw) if item.number == wanted), None)
