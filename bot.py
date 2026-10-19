import asyncio
import logging
import os
from datetime import datetime
from typing import Any

import httpx
from aiogram import Bot, Dispatcher, F
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
from aiogram.filters import Command, CommandStart
from aiogram.filters.command import CommandObject
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from dotenv import load_dotenv

load_dotenv()

DEFAULT_SHIKIMORI_GRAPHQL_URL = "https://shikimori.io/api/graphql"
DEFAULT_SHIKIMORI_SITE_URL = "https://shikimori.io"
MAX_PEOPLE_PER_SECTION = 20
MAX_MESSAGE_LENGTH = 3900

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

SHIKIMORI_SEARCH_QUERY = f"""
query SearchAnime($search: String!) {{
  animes(search: $search, limit: 5, order: popularity) {{
{SEARCH_FIELDS}
  }}
}}
"""

SHIKIMORI_BY_ID_QUERY = f"""
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


def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def create_bot() -> Bot:
    token = os.getenv("BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("BOT_TOKEN is not set. Copy .env.example to .env and add the bot token.")

    api_url = os.getenv("TELEGRAM_BOT_API_URL", "").strip().rstrip("/")
    if not api_url:
        return Bot(token=token)

    api = TelegramAPIServer.from_base(
        api_url,
        is_local=env_bool("TELEGRAM_BOT_API_LOCAL", False),
    )
    return Bot(token=token, session=AiohttpSession(api=api))


def shikimori_graphql_url() -> str:
    return os.getenv("SHIKIMORI_API_URL", DEFAULT_SHIKIMORI_GRAPHQL_URL).strip() or DEFAULT_SHIKIMORI_GRAPHQL_URL


def shikimori_site_url() -> str:
    return os.getenv("SHIKIMORI_SITE_URL", DEFAULT_SHIKIMORI_SITE_URL).strip().rstrip("/") or DEFAULT_SHIKIMORI_SITE_URL


async def shikimori_graphql(query: str, variables: dict[str, Any]) -> dict[str, Any]:
    headers = {
        "User-Agent": "anime-db-bot/0.1 (https://github.com/Winbil/anime-db-bot)",
        "Accept": "application/json",
    }
    api_url = shikimori_graphql_url()

    async with httpx.AsyncClient(timeout=15.0, headers=headers, follow_redirects=True) as client:
        response = await client.post(api_url, json={"query": query, "variables": variables})

    if response.is_error:
        preview = response.text.replace("\n", " ")[:800]
        raise RuntimeError(f"Shikimori HTTP {response.status_code} from {response.url}: {preview}")

    try:
        body = response.json()
    except ValueError as exc:
        preview = response.text.replace("\n", " ")[:800]
        raise RuntimeError(f"Shikimori returned non-JSON response from {response.url}: {preview}") from exc

    if body.get("errors"):
        messages = [error.get("message", str(error)) for error in body["errors"]]
        raise RuntimeError("Shikimori GraphQL error: " + "; ".join(messages))

    return body.get("data", {})


async def search_shikimori(query: str) -> list[dict[str, Any]]:
    data = await shikimori_graphql(SHIKIMORI_SEARCH_QUERY, {"search": query})
    return data.get("animes", [])


async def get_shikimori_anime(anime_id: str) -> dict[str, Any] | None:
    data = await shikimori_graphql(SHIKIMORI_BY_ID_QUERY, {"ids": anime_id})
    animes = data.get("animes", [])
    return animes[0] if animes else None


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).replace("\r", " ").split())


def dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        value = clean_text(value)
        key = value.casefold()
        if value and key not in seen:
            seen.add(key)
            result.append(value)
    return result


def format_date(value: dict[str, Any] | None) -> str:
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


def format_datetime(value: str | None) -> str:
    if not value:
        return ""
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M %Z").strip()
    except ValueError:
        return value


def person_name(person: dict[str, Any]) -> str:
    russian = clean_text(person.get("russian"))
    name = clean_text(person.get("name"))
    japanese = clean_text(person.get("japanese"))
    preferred = russian or name or japanese or "Неизвестно"
    extras = [item for item in dedupe([name, japanese]) if item.casefold() != preferred.casefold()]
    return f"{preferred} ({', '.join(extras)})" if extras else preferred


def people_lines(anime: dict[str, Any], want_seyu: bool) -> list[str]:
    rows: list[str] = []
    seen: set[tuple[str, str]] = set()
    for role in anime.get("personRoles") or []:
        person = role.get("person") or {}
        if bool(person.get("isSeyu")) != want_seyu:
            continue
        roles = dedupe(role.get("rolesRu") or role.get("rolesEn") or [])
        roles_text = ", ".join(roles) if roles else "роль не указана"
        name = person_name(person)
        key = (name.casefold(), roles_text.casefold())
        if key not in seen:
            seen.add(key)
            rows.append(f"• {name} — {roles_text}")
    return rows


def people_section(title: str, rows: list[str]) -> str:
    if not rows:
        return ""
    visible = rows[:MAX_PEOPLE_PER_SECTION]
    if len(rows) > len(visible):
        visible.append(f"…и ещё {len(rows) - len(visible)}")
    return title + "\n" + "\n".join(visible)


def anime_sections(anime: dict[str, Any]) -> list[str]:
    russian = clean_text(anime.get("russian"))
    name = clean_text(anime.get("name")) or "Без названия"
    title = russian or name

    kind = KIND_NAMES.get(anime.get("kind"), anime.get("kind") or "—")
    status = STATUS_NAMES.get(anime.get("status"), anime.get("status") or "—")
    rating = RATING_NAMES.get(anime.get("rating"), anime.get("rating") or "—")
    total = anime.get("episodes") or 0
    aired = anime.get("episodesAired") or 0
    episodes = f"{aired}/{total}" if total else str(aired or "—")

    studios = dedupe([studio.get("name", "") for studio in anime.get("studios") or []])
    genres = dedupe([genre.get("russian") or genre.get("name") or "" for genre in anime.get("genres") or []])
    licensors = dedupe(anime.get("licensors") or [])

    url = clean_text(anime.get("url"))
    if url.startswith("/"):
        url = f"{shikimori_site_url()}{url}"

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

    aired_on, released_on = format_date(anime.get("airedOn")), format_date(anime.get("releasedOn"))
    if aired_on != "—":
        info.append(f"Начало показа: {aired_on}")
    if released_on != "—":
        info.append(f"Окончание показа: {released_on}")

    next_episode = format_datetime(anime.get("nextEpisodeAt"))
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
    synonyms = [v for v in dedupe(anime.get("synonyms") or []) if v.casefold() not in seen_titles]
    if synonyms:
        titles.append("• Синонимы: " + "; ".join(synonyms))

    sections = ["\n".join(info), "\n".join(titles)]
    description = clean_text(anime.get("description"))
    if description:
        sections.append("Описание:\n" + description)

    staff = people_section("Авторы и команда:", people_lines(anime, want_seyu=False))
    voices = people_section("Сэйю / актёры озвучки:", people_lines(anime, want_seyu=True))
    if staff:
        sections.append(staff)
    if voices:
        sections.append(voices)
    return sections


def split_long_text(text: str, limit: int = MAX_MESSAGE_LENGTH) -> list[str]:
    text = text.strip()
    if len(text) <= limit:
        return [text] if text else []
    chunks: list[str] = []
    while len(text) > limit:
        split_at = text.rfind("\n", 0, limit)
        if split_at < limit // 2:
            split_at = text.rfind(" ", 0, limit)
        if split_at < limit // 2:
            split_at = limit
        chunks.append(text[:split_at].strip())
        text = text[split_at:].strip()
    if text:
        chunks.append(text)
    return chunks


def anime_text_chunks(anime: dict[str, Any]) -> list[str]:
    chunks: list[str] = []
    current = ""
    for section in anime_sections(anime):
        candidate = section if not current else current + "\n\n" + section
        if len(candidate) <= MAX_MESSAGE_LENGTH:
            current = candidate
            continue
        if current:
            chunks.append(current)
            current = ""
        section_chunks = split_long_text(section)
        chunks.extend(section_chunks[:-1])
        current = section_chunks[-1]
    if current:
        chunks.append(current)
    return chunks


def result_button_text(anime: dict[str, Any]) -> str:
    title = anime.get("russian") or anime.get("name") or "Без названия"
    year = (anime.get("airedOn") or {}).get("year")
    text = f"{title} ({year})" if year else title
    return text if len(text) <= 60 else text[:57] + "..."


def search_keyboard(animes: list[dict[str, Any]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[
            InlineKeyboardButton(text=result_button_text(anime), callback_data=f"anime:{anime['id']}")
        ] for anime in animes]
    )


async def send_anime_card(message: Message, anime: dict[str, Any]) -> None:
    poster_url = (anime.get("poster") or {}).get("mainUrl")
    title = clean_text(anime.get("russian")) or clean_text(anime.get("name")) or "Аниме"
    if poster_url:
        try:
            await message.answer_photo(photo=poster_url, caption=title[:1000])
        except Exception:
            logging.exception("Failed to send poster, continuing with text")
    for chunk in anime_text_chunks(anime):
        await message.answer(chunk)


dp = Dispatcher()


@dp.message(CommandStart())
async def start_handler(message: Message) -> None:
    await message.answer(
        "Привет! Это первая версия anime-db-bot.\n\n"
        "Команды:\n"
        "/anime <название> — найти аниме в Shikimori\n"
        "/ping — проверить, что бот работает"
    )


@dp.message(Command("ping"))
async def ping_handler(message: Message) -> None:
    await message.answer("pong")


@dp.message(Command("anime"))
async def anime_handler(message: Message, command: CommandObject) -> None:
    query = (command.args or "").strip()
    if not query:
        await message.answer("Использование: /anime <название>\nНапример: /anime slime")
        return
    try:
        animes = await search_shikimori(query)
    except Exception as exc:
        logging.error("Shikimori search failed: %s: %s", type(exc).__name__, exc, exc_info=True)
        await message.answer("Не удалось получить данные из Shikimori. Причина записана в лог бота.")
        return
    if not animes:
        await message.answer("Ничего не найдено.")
        return
    if len(animes) == 1:
        try:
            anime = await get_shikimori_anime(str(animes[0]["id"]))
        except Exception as exc:
            logging.error("Shikimori anime lookup failed: %s: %s", type(exc).__name__, exc, exc_info=True)
            await message.answer("Не удалось получить подробные данные из Shikimori. Причина записана в лог бота.")
            return
        if anime:
            await send_anime_card(message, anime)
        return
    await message.answer(
        f"Нашёл несколько вариантов по запросу «{query}». Выбери нужное аниме:",
        reply_markup=search_keyboard(animes),
    )


@dp.callback_query(F.data.startswith("anime:"))
async def anime_callback_handler(callback: CallbackQuery) -> None:
    anime_id = callback.data.split(":", 1)[1] if callback.data else ""
    if not anime_id.isdigit():
        await callback.answer("Некорректный ID.", show_alert=True)
        return
    await callback.answer()
    try:
        anime = await get_shikimori_anime(anime_id)
    except Exception as exc:
        logging.error("Shikimori anime lookup failed: %s: %s", type(exc).__name__, exc, exc_info=True)
        if callback.message:
            await callback.message.answer("Не удалось получить данные из Shikimori. Причина записана в лог бота.")
        return
    if anime is None or callback.message is None:
        return
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        logging.debug("Could not remove search keyboard", exc_info=True)
    await send_anime_card(callback.message, anime)


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")
    logging.info("Using Shikimori API: %s", shikimori_graphql_url())
    bot = create_bot()
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
