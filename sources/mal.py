from __future__ import annotations

import logging
from typing import Any

from core.http_client import http_request
from core.identity import AnimeIdentity
from core.models import AnimeRecord, BroadcastSlot, CharacterRecord, PersonCredit
from core.people_loading import PeopleBatch
from core.settings import SourceSettings, get_settings
from core.source_errors import SourceInvalidResponse
from core.source_keys import SourceKey
from core.temporal import parse_partial_date, parse_time
from localization import source_value_key
from sources.jikan import JIKAN_DISPLAY_NAME, JikanSource

DETAIL_FIELDS = ",".join(
    (
        "id", "title", "main_picture", "alternative_titles", "start_date",
        "end_date", "synopsis", "mean", "rank", "popularity", "num_list_users",
        "num_scoring_users", "num_favorites", "statistics", "media_type", "status",
        "genres", "num_episodes", "start_season", "broadcast", "source",
        "average_episode_duration", "rating", "pictures", "background", "studios",
    )
)


def _settings() -> SourceSettings:
    return get_settings().sources


def api_url() -> str:
    return _settings().mal_api_url


def client_id() -> str:
    value = _settings().mal_client_id
    if not value:
        raise RuntimeError("MAL_CLIENT_ID is empty. Add a MyAnimeList API Client ID to .env.")
    return value


def _clean(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).replace("\r", " ").split()).strip()


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        value = _clean(value)
        key = value.casefold()
        if value and key not in seen:
            seen.add(key)
            result.append(value)
    return result


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


def _season(value: dict[str, Any] | None) -> tuple[str | None, int | None]:
    value = value or {}
    raw = _clean(value.get("season")).casefold()
    year = _int(value.get("year"))
    season = source_value_key("mal", "season", raw, default=raw or None)
    return season, year


def _broadcast(value: dict[str, Any] | None) -> list[BroadcastSlot]:
    value = value or {}
    raw_day = _clean(value.get("day_of_the_week")).casefold()
    start_time = parse_time(_clean(value.get("start_time")))
    weekday = source_value_key("mal", "weekday", raw_day, default=raw_day or None)
    return [BroadcastSlot(weekday=weekday, time=start_time)] if weekday or start_time else []


def _status_distribution(value: dict[str, Any] | None) -> dict[str, int]:
    raw = (value or {}).get("status") or {}
    aliases = {
        "watching": "watching", "completed": "completed", "on_hold": "on_hold",
        "dropped": "dropped", "plan_to_watch": "planned",
    }
    result: dict[str, int] = {}
    for raw_key, raw_count in raw.items():
        key = aliases.get(_clean(raw_key).casefold())
        count = _int(raw_count)
        if key and count is not None and count >= 0:
            result[key] = count
    return result


def _posters(raw: dict[str, Any]) -> list[str]:
    urls: list[str] = []

    def add_picture(picture: dict[str, Any] | None) -> None:
        picture = picture or {}
        value = _clean(picture.get("large")) or _clean(picture.get("medium"))
        if value:
            urls.append(value)

    add_picture(raw.get("main_picture"))
    for picture in raw.get("pictures") or []:
        if isinstance(picture, dict):
            add_picture(picture)
    return _dedupe(urls)


async def _get_raw(mal_id: str, settings: SourceSettings | None = None) -> dict[str, Any] | None:
    settings = settings or _settings()
    if not settings.mal_client_id:
        raise RuntimeError("MAL_CLIENT_ID is empty. Add a MyAnimeList API Client ID to .env.")
    response = await http_request(
        "mal",
        "GET",
        f"{settings.mal_api_url}/anime/{mal_id}",
        operation="metadata",
        timeout=20.0,
        allowed_statuses={404},
        headers={
            "Accept": "application/json",
            "X-MAL-CLIENT-ID": settings.mal_client_id,
        },
        params={"fields": DETAIL_FIELDS},
    )
    if response.status_code == 404:
        return None
    try:
        return response.json()
    except ValueError as exc:
        preview = response.text.replace("\n", " ")[:800]
        raise SourceInvalidResponse(
            f"MyAnimeList returned non-JSON response: {preview}",
            source="mal",
            operation="metadata",
        ) from exc


def _record(raw: dict[str, Any]) -> AnimeRecord:
    mal_id = str(raw.get("id") or "").strip()
    title = _clean(raw.get("title"))
    alternative = raw.get("alternative_titles") or {}
    english = _clean(alternative.get("en"))
    japanese = _clean(alternative.get("ja"))
    titles = {key: value for key, value in {
        "romaji": title, "english": english, "japanese": japanese,
    }.items() if value}
    synonyms = _dedupe([
        *[_clean(value) for value in alternative.get("synonyms") or []], english, japanese,
    ])
    chosen_titles = {value.casefold() for value in titles.values() if value}
    synonyms = [value for value in synonyms if value.casefold() not in chosen_titles]

    duration_seconds = _int(raw.get("average_episode_duration"))
    duration_minutes = max(1, round(duration_seconds / 60)) if duration_seconds and duration_seconds > 0 else None
    episodes_total = _int(raw.get("num_episodes"))
    status_raw = _clean(raw.get("status")).casefold()
    episodes_aired = episodes_total if status_raw == "finished_airing" and episodes_total else None
    source_raw = _clean(raw.get("source")).casefold()
    source_material = source_value_key("mal", "source", source_raw, default=source_raw or None)
    genres = _dedupe([_clean(item.get("name")) for item in raw.get("genres") or [] if isinstance(item, dict)])
    studios = _dedupe([_clean(item.get("name")) for item in raw.get("studios") or [] if isinstance(item, dict)])
    synopsis = _clean(raw.get("synopsis"))
    background = _clean(raw.get("background"))
    media_type = _clean(raw.get("media_type")).casefold()
    rating_raw = _clean(raw.get("rating")).casefold()
    season, season_year = _season(raw.get("start_season"))

    return AnimeRecord(
        source=JIKAN_DISPLAY_NAME,
        source_id=mal_id,
        titles=titles,
        synonyms=synonyms,
        external_ids={"mal": mal_id} if mal_id else {},
        kind=source_value_key("mal", "media_type", media_type, default=media_type or None),
        status=source_value_key("mal", "status", status_raw, default=status_raw or None),
        rating=source_value_key("mal", "rating", rating_raw, default=rating_raw or None),
        season=season,
        season_year=season_year,
        episodes_total=episodes_total,
        episodes_aired=episodes_aired,
        duration_minutes=duration_minutes,
        aired_on=parse_partial_date(raw.get("start_date")),
        released_on=parse_partial_date(raw.get("end_date")),
        score=_float(raw.get("mean")),
        rank=_int(raw.get("rank")),
        popularity_rank=_int(raw.get("popularity")),
        list_users=_int(raw.get("num_list_users")),
        scoring_users=_int(raw.get("num_scoring_users")),
        favorites=_int(raw.get("num_favorites")),
        status_distribution=_status_distribution(raw.get("statistics")),
        genres=genres,
        studios=studios,
        source_materials=[source_material] if source_material else [],
        broadcasts=_broadcast(raw.get("broadcast")),
        descriptions={JIKAN_DISPLAY_NAME: synopsis} if synopsis else {},
        backgrounds=[background] if background else [],
        posters=_posters(raw),
        urls={"MyAnimeList": f"https://myanimelist.net/anime/{mal_id}"} if mal_id else {},
    )


class MALSource:
    name = JIKAN_DISPLAY_NAME
    source_key = SourceKey.MAL

    def __init__(self, settings: SourceSettings | None = None) -> None:
        self._settings = settings or _settings()
        self._jikan = JikanSource(self._settings)

    @property
    def settings(self) -> SourceSettings:
        return self._settings

    async def get_details(self, identity: AnimeIdentity) -> AnimeRecord | None:
        mal_id = str(identity.get("mal") or "").strip()
        if not mal_id.isdigit():
            return None
        raw = await _get_raw(mal_id, self.settings)
        if not raw or str(raw.get("id") or "") != mal_id:
            return None
        record = _record(raw)
        try:
            supplement = await self._jikan.load_metadata_supplement(identity)
        except Exception as exc:
            logging.warning(
                "Jikan MAL metadata supplement unavailable for %s: %s: %s",
                mal_id, type(exc).__name__, exc,
            )
            return record
        if supplement.get("licensors"):
            record.licensors = list(supplement["licensors"])
        if supplement.get("score_distribution"):
            record.score_distribution = dict(supplement["score_distribution"])
        return record

    async def load_characters(self, identity: AnimeIdentity) -> list[CharacterRecord]:
        return await self._jikan.load_characters(identity)

    async def load_staff(self, identity: AnimeIdentity) -> list[PersonCredit]:
        return await self._jikan.load_staff(identity)

    async def load_voices(self, identity: AnimeIdentity) -> list[PersonCredit]:
        return await self._jikan.load_voices(identity)

    async def load_staff_batch(self, identity: AnimeIdentity, *, cursor: str | None = None, portrait_limit: int = 50) -> PeopleBatch:
        return await self._jikan.load_staff_batch(identity, cursor=cursor, portrait_limit=portrait_limit)

    async def load_voices_batch(self, identity: AnimeIdentity, *, cursor: str | None = None, portrait_limit: int = 50) -> PeopleBatch:
        return await self._jikan.load_voices_batch(identity, cursor=cursor, portrait_limit=portrait_limit)
