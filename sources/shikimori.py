import os
from datetime import datetime
from typing import Any

import httpx

DEFAULT_SHIKIMORI_GRAPHQL_URL = "https://shikimori.io/api/graphql"
DEFAULT_SHIKIMORI_SITE_URL = "https://shikimori.io"

SEARCH_FIELDS = """
    id
    name
    russian
    airedOn { year }
"""

DETAIL_FIELDS = """
    id
    malId
    name
    russian
    english
    japanese
    synonyms
    licenseNameRu
    kind
    score
    status
    rating
    season
    episodes
    episodesAired
    duration
    franchise
    airedOn { year month day date }
    releasedOn { year month day date }
    nextEpisodeAt
    genres { id name russian kind }
    studios { id name }
    licensors
    personRoles {
      rolesRu
      rolesEn
      person { id name russian japanese isSeyu }
    }
    description
    poster { mainUrl }
    url
"""

SEARCH_QUERY = f"""
query SearchAnime($search: String!) {{
  animes(search: $search, limit: 5, order: popularity) {{
{SEARCH_FIELDS}
  }}
}}
"""

BY_ID_QUERY = f"""
query AnimeById($ids: String!) {{
  animes(ids: $ids, limit: 1) {{
{DETAIL_FIELDS}
  }}
}}
"""

STATUS_NAMES = {
    "anons": "анонсировано",
    "ongoing": "выходит",
    "released": "вышло",
}

KIND_NAMES = {
    "tv": "TV",
    "movie": "фильм",
    "ova": "OVA",
    "ona": "ONA",
    "special": "спешл",
    "tv_special": "TV-спешл",
    "music": "клип",
    "pv": "PV",
    "cm": "реклама",
}

RATING_NAMES = {
    "none": "без рейтинга",
    "g": "G",
    "pg": "PG",
    "pg_13": "PG-13",
    "r": "R-17+",
    "r_plus": "R+",
    "rx": "Rx",
}


def graphql_url() -> str:
    return (
        os.getenv("SHIKIMORI_API_URL", DEFAULT_SHIKIMORI_GRAPHQL_URL).strip()
        or DEFAULT_SHIKIMORI_GRAPHQL_URL
    )


def site_url() -> str:
    return (
        os.getenv("SHIKIMORI_SITE_URL", DEFAULT_SHIKIMORI_SITE_URL).strip().rstrip("/")
        or DEFAULT_SHIKIMORI_SITE_URL
    )


async def _graphql(query: str, variables: dict[str, Any]) -> dict[str, Any]:
    headers = {
        "User-Agent": "anime-db-bot/0.2 (https://github.com/Winbil/anime-db-bot)",
        "Accept": "application/json",
    }

    async with httpx.AsyncClient(
        timeout=15.0,
        headers=headers,
        follow_redirects=True,
    ) as client:
        response = await client.post(
            graphql_url(),
            json={"query": query, "variables": variables},
        )

    if response.is_error:
        preview = response.text.replace("\n", " ")[:800]
        raise RuntimeError(
            f"Shikimori HTTP {response.status_code} from {response.url}: {preview}"
        )

    try:
        body = response.json()
    except ValueError as exc:
        preview = response.text.replace("\n", " ")[:800]
        raise RuntimeError(
            f"Shikimori returned non-JSON response from {response.url}: {preview}"
        ) from exc

    if body.get("errors"):
        messages = [error.get("message", str(error)) for error in body["errors"]]
        raise RuntimeError("Shikimori GraphQL error: " + "; ".join(messages))

    return body.get("data", {})


async def search_anime(query: str) -> list[dict[str, Any]]:
    data = await _graphql(SEARCH_QUERY, {"search": query})
    return data.get("animes", [])


async def get_anime(anime_id: str) -> dict[str, Any] | None:
    data = await _graphql(BY_ID_QUERY, {"ids": anime_id})
    animes = data.get("animes", [])
    return animes[0] if animes else None


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).replace("\r", " ").split())


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        value = clean_text(value)
        key = value.casefold()
        if value and key not in seen:
            seen.add(key)
            result.append(value)
    return result


def _format_date(value: dict[str, Any] | None) -> str:
    if not value:
        return "—"
    if value.get("date"):
        return str(value["date"])

    year, month, day = value.get("year"), value.get("month"), value.get("day")
    if not year:
        return "—"

    result = f"{year:04d}"
    if month:
        result += f"-{month:02d}"
    if day:
        result += f"-{day:02d}"
    return result


def _format_datetime(value: str | None) -> str:
    if not value:
        return ""
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M %Z").strip()
    except ValueError:
        return value


def _person_name(person: dict[str, Any]) -> str:
    russian = clean_text(person.get("russian"))
    name = clean_text(person.get("name"))
    japanese = clean_text(person.get("japanese"))
    preferred = russian or name or japanese or "Неизвестно"
    extras = [
        item
        for item in _dedupe([name, japanese])
        if item.casefold() != preferred.casefold()
    ]
    return f"{preferred} ({', '.join(extras)})" if extras else preferred


def _people_lines(anime: dict[str, Any], want_seyu: bool) -> list[str]:
    rows: list[str] = []
    seen: set[tuple[str, str]] = set()

    for role in anime.get("personRoles") or []:
        person = role.get("person") or {}
        if bool(person.get("isSeyu")) != want_seyu:
            continue

        roles = _dedupe(role.get("rolesRu") or role.get("rolesEn") or [])
        roles_text = ", ".join(roles) if roles else "роль не указана"
        name = _person_name(person)
        key = (name.casefold(), roles_text.casefold())

        if key not in seen:
            seen.add(key)
            rows.append(f"• {name} — {roles_text}")

    return rows


def _people_section(
    title: str,
    rows: list[str],
    limit: int | None,
) -> str:
    if not rows:
        return ""

    visible = rows if limit is None else rows[:limit]
    result = list(visible)

    if limit is not None and len(rows) > len(visible):
        result.append(f"…и ещё {len(rows) - len(visible)}")

    return title + "\n" + "\n".join(result)


def anime_title(anime: dict[str, Any]) -> str:
    return (
        clean_text(anime.get("russian"))
        or clean_text(anime.get("name"))
        or "Аниме"
    )


def poster_url(anime: dict[str, Any]) -> str | None:
    return (anime.get("poster") or {}).get("mainUrl")


def result_button_text(anime: dict[str, Any]) -> str:
    title = anime.get("russian") or anime.get("name") or "Без названия"
    year = (anime.get("airedOn") or {}).get("year")
    text = f"{title} ({year})" if year else title
    return text if len(text) <= 60 else text[:57] + "..."


def anime_sections(
    anime: dict[str, Any],
    people_limit: int | None = 20,
) -> list[str]:
    russian = clean_text(anime.get("russian"))
    name = clean_text(anime.get("name")) or "Без названия"
    title = russian or name

    kind = KIND_NAMES.get(anime.get("kind"), anime.get("kind") or "—")
    status = STATUS_NAMES.get(anime.get("status"), anime.get("status") or "—")
    rating = RATING_NAMES.get(anime.get("rating"), anime.get("rating") or "—")

    total = anime.get("episodes") or 0
    aired = anime.get("episodesAired") or 0
    episodes = f"{aired}/{total}" if total else str(aired or "—")

    studios = _dedupe(
        [studio.get("name", "") for studio in anime.get("studios") or []]
    )
    genres = _dedupe(
        [
            genre.get("russian") or genre.get("name") or ""
            for genre in anime.get("genres") or []
        ]
    )
    licensors = _dedupe(anime.get("licensors") or [])

    url = clean_text(anime.get("url"))
    if url.startswith("/"):
        url = f"{site_url()}{url}"

    info = [
        title,
        "",
        f"Тип: {kind}",
        f"Статус: {status}",
        f"Серии: {episodes}",
        f"Оценка Shikimori: {anime.get('score') or '—'}",
        f"Возрастной рейтинг: {rating}",
    ]

    if anime.get("duration"):
        info.append(f"Длительность серии: {anime['duration']} мин.")
    if anime.get("season"):
        info.append(f"Сезон: {anime['season']}")
    if anime.get("franchise"):
        info.append(f"Франшиза: {anime['franchise']}")

    aired_on = _format_date(anime.get("airedOn"))
    released_on = _format_date(anime.get("releasedOn"))
    if aired_on != "—":
        info.append(f"Начало показа: {aired_on}")
    if released_on != "—":
        info.append(f"Окончание показа: {released_on}")

    next_episode = _format_datetime(anime.get("nextEpisodeAt"))
    if next_episode:
        info.append(f"Следующая серия: {next_episode}")
    if genres:
        info.append(f"Жанры: {', '.join(genres)}")
    if studios:
        info.append(f"Студии: {', '.join(studios)}")
    if licensors:
        info.append(f"Лицензиаты: {', '.join(licensors)}")

    ids = [f"Shikimori ID: {anime.get('id')}"]
    if anime.get("malId"):
        ids.append(f"MAL ID: {anime['malId']}")
    info.append(" | ".join(ids))

    if url:
        info.append(url)

    titles = ["Названия:"]
    title_entries = [
        ("Русское", russian),
        ("Оригинальное / romaji", name),
        ("English", clean_text(anime.get("english"))),
        ("日本語", clean_text(anime.get("japanese"))),
        ("Лицензионное RU", clean_text(anime.get("licenseNameRu"))),
    ]

    seen_titles: set[str] = set()
    for label, value in title_entries:
        if value and value.casefold() not in seen_titles:
            seen_titles.add(value.casefold())
            titles.append(f"• {label}: {value}")

    synonyms = [
        value
        for value in _dedupe(anime.get("synonyms") or [])
        if value.casefold() not in seen_titles
    ]
    if synonyms:
        titles.append("• Синонимы: " + "; ".join(synonyms))

    sections = ["\n".join(info), "\n".join(titles)]

    description = clean_text(anime.get("description"))
    if description:
        sections.append("Описание:\n" + description)

    staff = _people_section(
        "Авторы и команда:",
        _people_lines(anime, want_seyu=False),
        people_limit,
    )
    voices = _people_section(
        "Сэйю / актёры озвучки:",
        _people_lines(anime, want_seyu=True),
        people_limit,
    )

    if staff:
        sections.append(staff)
    if voices:
        sections.append(voices)

    return sections


def anime_text(
    anime: dict[str, Any],
    people_limit: int | None = 20,
) -> str:
    return "\n\n".join(anime_sections(anime, people_limit=people_limit))
