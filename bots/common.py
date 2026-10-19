import html
import logging
import os

from aiogram import Bot, Dispatcher, F
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
from aiogram.filters import Command, CommandStart
from aiogram.filters.command import CommandObject
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputRichMessage,
    Message,
)
from dotenv import load_dotenv

from sources import shikimori

load_dotenv()

OFFICIAL_MESSAGE_LIMIT = 3900
RICH_MESSAGE_LIMIT = 32000
OFFICIAL_PEOPLE_LIMIT = 20


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def create_bot(use_custom_api: bool) -> Bot:
    token = os.getenv("BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError(
            "BOT_TOKEN is not set. Copy .env.example to .env and add the bot token."
        )

    if not use_custom_api:
        return Bot(token=token)

    api_url = os.getenv("TELEGRAM_BOT_API_URL", "").strip().rstrip("/")
    if not api_url:
        raise RuntimeError(
            "TELEGRAM_BOT_API_URL is empty, but the tg-bot-api launcher was selected."
        )

    api = TelegramAPIServer.from_base(
        api_url,
        is_local=_env_bool("TELEGRAM_BOT_API_LOCAL", False),
    )
    return Bot(token=token, session=AiohttpSession(api=api))


def _split_text(text: str, limit: int) -> list[str]:
    text = text.strip()
    if not text:
        return []
    if len(text) <= limit:
        return [text]

    chunks: list[str] = []

    while len(text) > limit:
        split_at = text.rfind("\n\n", 0, limit)
        if split_at < limit // 2:
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


def _plain_text_to_rich_html(text: str) -> str:
    paragraphs: list[str] = []
    for paragraph in text.split("\n\n"):
        escaped = html.escape(paragraph).replace("\n", "<br>")
        if escaped:
            paragraphs.append(f"<p>{escaped}</p>")
    return "".join(paragraphs)


async def _send_standard_text(message: Message, text: str) -> None:
    for chunk in _split_text(text, OFFICIAL_MESSAGE_LIMIT):
        await message.answer(chunk)


async def _send_rich_text(message: Message, text: str) -> None:
    for chunk in _split_text(text, RICH_MESSAGE_LIMIT):
        rich = InputRichMessage(html=_plain_text_to_rich_html(chunk))
        await message.answer_rich(rich)


def _search_keyboard(animes: list[dict]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=shikimori.result_button_text(anime),
                    callback_data=f"anime:{anime['id']}",
                )
            ]
            for anime in animes
        ]
    )


async def _send_anime_card(
    message: Message,
    anime: dict,
    rich_mode: bool,
) -> None:
    poster = shikimori.poster_url(anime)
    title = shikimori.anime_title(anime)

    if poster:
        try:
            await message.answer_photo(photo=poster, caption=title[:1000])
        except Exception:
            logging.exception("Failed to send poster, continuing with text")

    people_limit = None if rich_mode else OFFICIAL_PEOPLE_LIMIT
    text = shikimori.anime_text(anime, people_limit=people_limit)

    if not rich_mode:
        await _send_standard_text(message, text)
        return

    try:
        await _send_rich_text(message, text)
    except Exception:
        logging.exception(
            "sendRichMessage failed; falling back to standard sendMessage chunks"
        )
        await _send_standard_text(message, text)


def build_dispatcher(rich_mode: bool) -> Dispatcher:
    dp = Dispatcher()

    @dp.message(CommandStart())
    async def start_handler(message: Message) -> None:
        mode = (
            "tg-bot-api + sendRichMessage"
            if rich_mode
            else "официальный Bot API + sendMessage"
        )
        await message.answer(
            "Привет! Это anime-db-bot.\n\n"
            f"Режим: {mode}\n\n"
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
            await message.answer(
                "Использование: /anime <название>\nНапример: /anime slime"
            )
            return

        try:
            animes = await shikimori.search_anime(query)
        except Exception as exc:
            logging.error(
                "Shikimori search failed: %s: %s",
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
            await _load_and_send(message, str(animes[0]["id"]), rich_mode)
            return

        await message.answer(
            f"Нашёл несколько вариантов по запросу «{query}». "
            "Выбери нужное аниме:",
            reply_markup=_search_keyboard(animes),
        )

    @dp.callback_query(F.data.startswith("anime:"))
    async def anime_callback_handler(callback: CallbackQuery) -> None:
        anime_id = callback.data.split(":", 1)[1] if callback.data else ""
        if not anime_id.isdigit():
            await callback.answer("Некорректный ID.", show_alert=True)
            return

        await callback.answer()

        if callback.message is None:
            return

        try:
            await callback.message.edit_reply_markup(reply_markup=None)
        except Exception:
            logging.debug("Could not remove search keyboard", exc_info=True)

        await _load_and_send(callback.message, anime_id, rich_mode)

    return dp


async def _load_and_send(
    message: Message,
    anime_id: str,
    rich_mode: bool,
) -> None:
    try:
        anime = await shikimori.get_anime(anime_id)
    except Exception as exc:
        logging.error(
            "Shikimori anime lookup failed: %s: %s",
            type(exc).__name__,
            exc,
            exc_info=True,
        )
        await message.answer(
            "Не удалось получить подробные данные из Shikimori. "
            "Причина записана в лог бота."
        )
        return

    if anime is None:
        await message.answer("Аниме не найдено.")
        return

    await _send_anime_card(message, anime, rich_mode)


async def run_bot(
    *,
    use_custom_api: bool,
    rich_mode: bool,
    mode_name: str,
) -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    logging.info("Bot mode: %s", mode_name)
    logging.info("Using Shikimori API: %s", shikimori.graphql_url())

    bot = create_bot(use_custom_api=use_custom_api)
    dp = build_dispatcher(rich_mode=rich_mode)

    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()
