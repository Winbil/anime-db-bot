import asyncio
import logging
import os
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

ANIME_FIELDS = """
    id
    name
    russian
    kind
    score
    status
    episodes
    episodesAired
    airedOn {
      year
    }
    poster {
      mainUrl
    }
    url
"""

SHIKIMORI_SEARCH_QUERY = f"""
query SearchAnime($search: String!) {{
  animes(search: $search, limit: 5, order: popularity) {{
{ANIME_FIELDS}
  }}
}}
"""

SHIKIMORI_BY_ID_QUERY = f"""
query AnimeById($ids: String!) {{
  animes(ids: $ids, limit: 1) {{
{ANIME_FIELDS}
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
    session = AiohttpSession(api=api)
    return Bot(token=token, session=session)


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

    async with httpx.AsyncClient(
        timeout=15.0,
        headers=headers,
        follow_redirects=True,
    ) as client:
        response = await client.post(
            api_url,
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


async def search_shikimori(query: str) -> list[dict[str, Any]]:
    data = await shikimori_graphql(
        SHIKIMORI_SEARCH_QUERY,
        {"search": query},
    )
    return data.get("animes", [])


async def get_shikimori_anime(anime_id: str) -> dict[str, Any] | None:
    data = await shikimori_graphql(
        SHIKIMORI_BY_ID_QUERY,
        {"ids": anime_id},
    )
    animes = data.get("animes", [])
    return animes[0] if animes else None


def anime_text(anime: dict[str, Any]) -> str:
    russian = anime.get("russian")
    name = anime.get("name") or "Без названия"
    title = russian or name
    if russian and name and russian != name:
        title += f"\n{name}"

    kind = KIND_NAMES.get(anime.get("kind"), anime.get("kind") or "—")
    status = STATUS_NAMES.get(anime.get("status"), anime.get("status") or "—")
    score = anime.get("score") or "—"
    year = (anime.get("airedOn") or {}).get("year") or "—"

    total = anime.get("episodes") or 0
    aired = anime.get("episodesAired") or 0
    episodes = f"{aired}/{total}" if total else str(aired or "—")

    url = anime.get("url") or ""
    if url.startswith("/"):
        url = f"{shikimori_site_url()}{url}"

    lines = [
        title,
        "",
        f"Тип: {kind}",
        f"Статус: {status}",
        f"Год: {year}",
        f"Серии: {episodes}",
        f"Оценка Shikimori: {score}",
    ]
    if url:
        lines.extend(["", url])

    return "\n".join(lines)


def result_button_text(anime: dict[str, Any]) -> str:
    title = anime.get("russian") or anime.get("name") or "Без названия"
    year = (anime.get("airedOn") or {}).get("year")
    suffix = f" ({year})" if year else ""
    text = f"{title}{suffix}"
    return text if len(text) <= 60 else text[:57] + "..."


def search_keyboard(animes: list[dict[str, Any]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=result_button_text(anime),
                    callback_data=f"anime:{anime['id']}",
                )
            ]
            for anime in animes
        ]
    )


async def send_anime_card(message: Message, anime: dict[str, Any]) -> None:
    text = anime_text(anime)
    poster_url = (anime.get("poster") or {}).get("mainUrl")

    if poster_url:
        try:
            await message.answer_photo(photo=poster_url, caption=text)
            return
        except Exception:
            logging.exception("Failed to send poster, falling back to text")

    await message.answer(text)


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
        logging.error(
            "Shikimori request failed: %s: %s",
            type(exc).__name__,
            exc,
            exc_info=True,
        )
        await message.answer(
            "Не удалось получить данные из Shikimori. Причина записана в лог бота."
        )
        return

    if not animes:
        await message.answer("Ничего не найдено.")
        return

    if len(animes) == 1:
        await send_anime_card(message, animes[0])
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
        logging.error(
            "Shikimori anime lookup failed: %s: %s",
            type(exc).__name__,
            exc,
            exc_info=True,
        )
        await callback.answer("Не удалось получить данные из Shikimori.", show_alert=True)
        return

    if anime is None or callback.message is None:
        await callback.answer("Аниме не найдено.", show_alert=True)
        return

    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        logging.debug("Could not remove search keyboard", exc_info=True)

    await send_anime_card(callback.message, anime)


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    logging.info("Using Shikimori API: %s", shikimori_graphql_url())

    bot = create_bot()
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
