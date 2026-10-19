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

STANDARD_MESSAGE_LIMIT = 3900
RICH_MESSAGE_LIMIT = 32000

SECTION_LABELS = {
    "main": "Основное",
    "titles": "Названия",
    "description": "Описание",
    "staff": "Команда",
    "voices": "Сэйю",
}


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
        return ["Нет данных."]
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


def _rich(text: str) -> InputRichMessage:
    return InputRichMessage(html=_plain_text_to_rich_html(text))


def _main_rich(anime_id: str, text: str) -> InputRichMessage:
    base = _plain_text_to_rich_html(text)
    links = (
        "<p><b>Подробная информация</b><br>"
        f'<tg-button type="callback_data" style="link" data="av:{anime_id}:description:0">Описание</tg-button>'
        " — нажмите, чтобы открыть<br>"
        f'<tg-button type="callback_data" style="link" data="av:{anime_id}:titles:0">Все названия</tg-button>'
        " — нажмите, чтобы открыть<br>"
        f'<tg-button type="callback_data" style="link" data="av:{anime_id}:staff:0">Авторы и команда</tg-button>'
        " — нажмите, чтобы открыть<br>"
        f'<tg-button type="callback_data" style="link" data="av:{anime_id}:voices:0">Сэйю</tg-button>'
        " — нажмите, чтобы открыть</p>"
    )
    return InputRichMessage(html=base + links)


async def _send_standard_text(
    message: Message,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> None:
    chunks = _split_text(text, STANDARD_MESSAGE_LIMIT)
    for index, chunk in enumerate(chunks):
        await message.answer(
            chunk,
            reply_markup=reply_markup if index == len(chunks) - 1 else None,
        )


def _anime_sections(anime: dict) -> dict[str, str]:
    sections = shikimori.anime_sections(anime, people_limit=None)

    result = {
        "main": sections[0] if sections else shikimori.anime_title(anime),
        "titles": "Названия:\nНет данных.",
        "description": "Описание:\nНет данных.",
        "staff": "Авторы и команда:\nНет данных.",
        "voices": "Сэйю / актёры озвучки:\nНет данных.",
    }

    for section in sections[1:]:
        if section.startswith("Названия:"):
            result["titles"] = section
        elif section.startswith("Описание:"):
            result["description"] = section
        elif section.startswith("Авторы и команда:"):
            result["staff"] = section
        elif section.startswith("Сэйю / актёры озвучки:"):
            result["voices"] = section

    return result


def _view_pages(anime: dict, section: str) -> list[str]:
    text = _anime_sections(anime).get(section) or "Нет данных."
    return _split_text(text, RICH_MESSAGE_LIMIT)


def _navigation_keyboard(
    anime_id: str,
    current_section: str,
    page: int,
    page_count: int,
) -> InlineKeyboardMarkup | None:
    rows: list[list[InlineKeyboardButton]] = []

    if current_section != "main":
        rows.append(
            [
                InlineKeyboardButton(
                    text="← Назад",
                    callback_data=f"av:{anime_id}:main:0",
                )
            ]
        )

    if page_count > 1:
        nav: list[InlineKeyboardButton] = []
        if page > 0:
            nav.append(
                InlineKeyboardButton(
                    text="◀️",
                    callback_data=f"av:{anime_id}:{current_section}:{page - 1}",
                )
            )
        nav.append(
            InlineKeyboardButton(
                text=f"{page + 1}/{page_count}",
                callback_data="noop",
            )
        )
        if page + 1 < page_count:
            nav.append(
                InlineKeyboardButton(
                    text="▶️",
                    callback_data=f"av:{anime_id}:{current_section}:{page + 1}",
                )
            )
        rows.append(nav)

    return InlineKeyboardMarkup(inline_keyboard=rows) if rows else None


def _fallback_main_keyboard(anime_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Описание",
                    callback_data=f"av:{anime_id}:description:0",
                ),
                InlineKeyboardButton(
                    text="Названия",
                    callback_data=f"av:{anime_id}:titles:0",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="Команда",
                    callback_data=f"av:{anime_id}:staff:0",
                ),
                InlineKeyboardButton(
                    text="Сэйю",
                    callback_data=f"av:{anime_id}:voices:0",
                ),
            ],
        ]
    )


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


def _rich_view(anime_id: str, section: str, text: str) -> InputRichMessage:
    if section == "main":
        return _main_rich(anime_id, text)
    return _rich(text)


async def _send_anime_view(
    message: Message,
    anime: dict,
    section: str = "main",
    page: int = 0,
) -> None:
    anime_id = str(anime.get("id") or "")
    pages = _view_pages(anime, section)
    page = max(0, min(page, len(pages) - 1))
    keyboard = _navigation_keyboard(anime_id, section, page, len(pages))
    text = pages[page]

    try:
        await message.answer_rich(
            _rich_view(anime_id, section, text),
            reply_markup=keyboard,
        )
    except Exception:
        logging.exception(
            "sendRichMessage failed; falling back to standard sendMessage"
        )
        fallback_keyboard = (
            _fallback_main_keyboard(anime_id) if section == "main" else keyboard
        )
        await _send_standard_text(
            message,
            text,
            reply_markup=fallback_keyboard,
        )


async def _edit_anime_view(
    message: Message,
    anime: dict,
    section: str,
    page: int,
) -> None:
    anime_id = str(anime.get("id") or "")
    pages = _view_pages(anime, section)
    page = max(0, min(page, len(pages) - 1))
    keyboard = _navigation_keyboard(anime_id, section, page, len(pages))
    text = pages[page]

    try:
        await message.edit_text(
            rich_message=_rich_view(anime_id, section, text),
            reply_markup=keyboard,
        )
    except Exception:
        logging.exception(
            "Rich message edit failed; falling back to standard text edit"
        )
        standard_page = _split_text(text, STANDARD_MESSAGE_LIMIT)[0]
        fallback_keyboard = (
            _fallback_main_keyboard(anime_id) if section == "main" else keyboard
        )
        await message.edit_text(
            text=standard_page,
            reply_markup=fallback_keyboard,
        )


async def _send_anime_card(message: Message, anime: dict) -> None:
    poster = shikimori.poster_url(anime)
    title = shikimori.anime_title(anime)

    if poster:
        try:
            await message.answer_photo(photo=poster, caption=title[:1000])
        except Exception:
            logging.exception("Failed to send poster, continuing with text")

    await _send_anime_view(message, anime, section="main", page=0)


def build_dispatcher(mode_name: str) -> Dispatcher:
    dp = Dispatcher()

    @dp.message(CommandStart())
    async def start_handler(message: Message) -> None:
        await message.answer(
            "Привет! Это anime-db-bot.\n\n"
            f"Режим: {mode_name}\n"
            "Подробные карточки используют sendRichMessage.\n\n"
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
            await _load_and_send(message, str(animes[0]["id"]))
            return

        await message.answer(
            f"Нашёл несколько вариантов по запросу «{query}». "
            "Выбери нужное аниме:",
            reply_markup=_search_keyboard(animes),
        )

    @dp.callback_query(F.data == "noop")
    async def noop_callback(callback: CallbackQuery) -> None:
        await callback.answer()

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

        await _load_and_send(callback.message, anime_id)

    @dp.callback_query(F.data.startswith("av:"))
    async def anime_view_callback_handler(callback: CallbackQuery) -> None:
        data = (callback.data or "").split(":")
        if len(data) != 4:
            await callback.answer("Некорректная команда.", show_alert=True)
            return

        _, anime_id, section, page_text = data
        if (
            not anime_id.isdigit()
            or section not in SECTION_LABELS
            or not page_text.isdigit()
        ):
            await callback.answer("Некорректная команда.", show_alert=True)
            return

        if callback.message is None:
            await callback.answer()
            return

        await callback.answer()

        try:
            anime = await shikimori.get_anime(anime_id)
        except Exception as exc:
            logging.error(
                "Shikimori anime view lookup failed: %s: %s",
                type(exc).__name__,
                exc,
                exc_info=True,
            )
            await callback.answer(
                "Не удалось обновить карточку.",
                show_alert=True,
            )
            return

        if anime is None:
            await callback.answer("Аниме не найдено.", show_alert=True)
            return

        await _edit_anime_view(
            callback.message,
            anime,
            section=section,
            page=int(page_text),
        )

    return dp


async def _load_and_send(message: Message, anime_id: str) -> None:
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

    await _send_anime_card(message, anime)


async def run_bot(*, use_custom_api: bool, mode_name: str) -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    logging.info("Bot mode: %s", mode_name)
    logging.info("Anime details use rich-text callback links and inline navigation")
    logging.info("Using Shikimori API: %s", shikimori.graphql_url())

    bot = create_bot(use_custom_api=use_custom_api)
    dp = build_dispatcher(mode_name=mode_name)

    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()
