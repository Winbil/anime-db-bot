from __future__ import annotations

import os
from typing import Any

import httpx

from core.http_config import USER_AGENT
from core.models import AnimeRecord

DEFAULT_MAL_API_URL = "https://api.myanimelist.net/v2"

DETAIL_FIELDS = ",".join(
    (
        "id",
        "title",
        "main_picture",
        "alternative_titles",
        "start_date",
        "end_date",
        "synopsis",
        "mean",
        "rank",
        "popularity",
        "num_list_users",
        "num_scoring_users",
        "num_favorites",
        "media_type",
        "status",
        "genres",
        "num_episodes",
        "start_season",
        "broadcast",
        "source",
        "average_episode_duration",
        "rating",
        "pictures",
        "background",
        "studios",
    )
)

MEDIA_TYPE_NAMES = {
    "tv": "TV",
    "ova": "OVA",
    "movie": "фильм",
    "special": "спешл",
    "ona": "ONA",
    "music": "клип",
    "unknown": "неизвестно",
}

STATUS_NAMES = {
    "finished_airing": "вышло",
    "currently_airing": "выходит",
    "not_yet_aired": "анонсировано",
}

RATING_NAMES = {
    "g": "G",
    "pg": "PG",
    "pg_13": "PG-13",
    "r": "R-17+",
    "r+": "R+",
    "rx": "Rx",
}

SEASON_NAMES = {
    "winter": "Зима",
    "spring": "Весна",
    "summer": "Лето",
    "fall": "Осень",
}

SOURCE_NAMES = {
    "original": "Оригинал",
    "manga": "Манга",
    "4_koma_manga": "4-кома манга",
    "web_manga": "Веб-манга",
    "digital_manga": "Цифровая манга",
    "novel": "Роман",
    "light_novel": "Ранобэ",
    "visual_novel": "Визуальная новелла",
    "game": "Игра",
    "card_game": "Карточная игра",
    "book": "Книга",
    "picture_book": "Иллюстрированная книга",
    "radio": "Радио",
    "music": "Музыка",
    "other": "Другое",
}

DAY_NAMES = {
    "monday": "Понедельник",
    "tuesday": "Вторник",
    "wednesday": "Среда",
    "thursday": "Четверг",
    "friday": "Пятница",
    "saturday": "Суббота",
    "sunday": "Воскресенье",
    "other": "Другое",
}


def api_url() -> str:
    return (
        os.getenv("MAL_API_URL", DEFAULT_MAL_API_URL).strip().rstrip("/")
        or DEFAULT_MAL_API_URL
    )


def client_id() -> str:
    value = os.getenv("MAL_CLIENT_ID", "").strip()
    if not value:
        raise RuntimeError(
            "MAL_CLIENT_ID is empty. Add a MyAnimeList API Client ID to .env."
        )
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


def _season(value: dict[str, Any] | None) -> str | None:
    value = value or {}
    season = _clean(value.get("season")).casefold()
    year = _int(value.get("year"))
    season_name = SEASON_NAMES.get(season, season.title() if season else "")
    result = " ".join(part for part in (season_name, str(year) if year else "") if part)
    return result or None


def _broadcast(value: dict[str, Any] | None) -> list[str]:
    value = value or {}
    day = _clean(value.get("day_of_the_week")).casefold()
    time = _clean(value.get("start_time"))
    day_name = DAY_NAMES.get(day, day.title() if day else "")
    text = " ".join(part for part in (day_name, time) if part)
    return [text] if text else []


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


async def _get_raw(mal_id: str) -> dict[str, Any] | None:
    headers = {
        "Accept": "application/json",
        "User-Agent": USER_AGENT,
        "X-MAL-CLIENT-ID": client_id(),
    }

    async with httpx.AsyncClient(
        timeout=20.0,
        headers=headers,
        follow_redirects=True,
    ) as client:
        response = await client.get(
            f"{api_url()}/anime/{mal_id}",
            params={"fields": DETAIL_FIELDS},
        )

    if response.status_code == 404:
        return None
    if response.is_error:
        preview = response.text.replace("\n", " ")[:800]
        if response.status_code in {401, 403}:
            raise RuntimeError(
                f"MyAnimeList rejected MAL_CLIENT_ID (HTTP {response.status_code}): {preview}"
            )
        raise RuntimeError(
            f"MyAnimeList HTTP {response.status_code} from {response.url}: {preview}"
        )

    try:
        return response.json()
    except ValueError as exc:
        preview = response.text.replace("\n", " ")[:800]
        raise RuntimeError(f"MyAnimeList returned non-JSON response: {preview}") from exc


def _record(raw: dict[str, Any]) -> AnimeRecord:
    mal_id = str(raw.get("id") or "").strip()
    title = _clean(raw.get("title"))
    alternative = raw.get("alternative_titles") or {}
    english = _clean(alternative.get("en"))
    japanese = _clean(alternative.get("ja"))

    titles = {
        key: value
        for key, value in {
            "romaji": title,
            "english": english,
            "japanese": japanese,
        }.items()
        if value
    }

    synonyms = _dedupe(
        [
            *[_clean(value) for value in alternative.get("synonyms") or []],
            english,
            japanese,
        ]
    )
    chosen_titles = {value.casefold() for value in titles.values() if value}
    synonyms = [value for value in synonyms if value.casefold() not in chosen_titles]

    duration_seconds = _int(raw.get("average_episode_duration"))
    duration_minutes = (
        max(1, round(duration_seconds / 60))
        if duration_seconds and duration_seconds > 0
        else None
    )

    episodes_total = _int(raw.get("num_episodes"))
    status_raw = _clean(raw.get("status")).casefold()
    episodes_aired = (
        episodes_total
        if status_raw == "finished_airing" and episodes_total
        else None
    )

    source_raw = _clean(raw.get("source")).casefold()
    source_material = SOURCE_NAMES.get(
        source_raw,
        source_raw.replace("_", " ").title() if source_raw else "",
    )

    genres = _dedupe(
        [
            _clean(item.get("name"))
            for item in raw.get("genres") or []
            if isinstance(item, dict)
        ]
    )
    studios = _dedupe(
        [
            _clean(item.get("name"))
            for item in raw.get("studios") or []
            if isinstance(item, dict)
        ]
    )

    synopsis = _clean(raw.get("synopsis"))
    background = _clean(raw.get("background"))

    return AnimeRecord(
        source="MyAnimeList",
        source_id=mal_id,
        titles=titles,
        synonyms=synonyms,
        external_ids={"mal": mal_id} if mal_id else {},
        kind=MEDIA_TYPE_NAMES.get(
            _clean(raw.get("media_type")).casefold(),
            _clean(raw.get("media_type")) or None,
        ),
        status=STATUS_NAMES.get(status_raw, status_raw or None),
        rating=RATING_NAMES.get(
            _clean(raw.get("rating")).casefold(),
            _clean(raw.get("rating")) or None,
        ),
        season=_season(raw.get("start_season")),
        episodes_total=episodes_total,
        episodes_aired=episodes_aired,
        duration_minutes=duration_minutes,
        aired_on=_clean(raw.get("start_date")) or None,
        released_on=_clean(raw.get("end_date")) or None,
        score=_float(raw.get("mean")),
        rank=_int(raw.get("rank")),
        popularity_rank=_int(raw.get("popularity")),
        list_users=_int(raw.get("num_list_users")),
        scoring_users=_int(raw.get("num_scoring_users")),
        favorites=_int(raw.get("num_favorites")),
        genres=genres,
        studios=studios,
        source_materials=[source_material] if source_material else [],
        broadcasts=_broadcast(raw.get("broadcast")),
        descriptions={"MyAnimeList": synopsis} if synopsis else {},
        backgrounds=[background] if background else [],
        posters=_posters(raw),
        urls={
            "MyAnimeList": f"https://myanimelist.net/anime/{mal_id}"
        } if mal_id else {},
    )


class MALSource:
    name = "MyAnimeList"

    async def get_details(
        self,
        mal_id: str,
        known_ids: dict[str, str],
    ) -> AnimeRecord | None:
        mal_id = str(mal_id).strip()
        if not mal_id.isdigit():
            return None

        raw = await _get_raw(mal_id)
        if not raw:
            return None
        if str(raw.get("id") or "") != mal_id:
            return None
        return _record(raw)
