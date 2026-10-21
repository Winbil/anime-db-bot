from __future__ import annotations

from aiogram import Dispatcher, F
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, Message

from bots.telegram import common as common_bot


def build_dispatcher(mode_name: str) -> Dispatcher:
    """Build the core dispatcher without search-provider-specific handlers."""
    dp = Dispatcher()

    @dp.message(CommandStart())
    async def start_handler(message: Message) -> None:
        source_names = ", ".join(source.name for source in common_bot.SOURCES) or "нет"
        await message.answer(
            "Привет! Это anime-db-bot.\n\n"
            f"Режим Telegram: {mode_name}\n"
            f"Основной поиск: {common_bot.SEARCH_SERVICE.provider_name}\n"
            f"Источники данных: {source_names}\n\n"
            "После выбора MAL ID бот собирает и объединяет метаданные всех доступных источников без повторений.\n\n"
            "Команды:\n"
            "/anime <название> — общий поиск\n"
            "/search <название> — выбрать конкретные поисковики\n"
            "/ping — проверить, что бот работает"
        )

    @dp.message(Command("ping"))
    async def ping_handler(message: Message) -> None:
        await message.answer("pong")

    @dp.callback_query(F.data == "noop")
    async def noop_callback(callback: CallbackQuery) -> None:
        await callback.answer()

    @dp.callback_query(F.data.startswith("ad:"))
    async def description_source_callback_handler(callback: CallbackQuery) -> None:
        data = (callback.data or "").split(":")
        if len(data) != 4 or not data[2].isdigit() or not data[3].isdigit():
            await callback.answer("Некорректное описание.", show_alert=True)
            return

        _, token, source_index_text, page_text = data
        anime = common_bot.ANIME_SESSIONS.get(token)
        if anime is None:
            await callback.answer(
                "Карточка устарела. Выполни поиск ещё раз.",
                show_alert=True,
            )
            return
        if callback.message is None:
            await callback.answer()
            return

        source_index = int(source_index_text)
        if source_index >= len(common_bot._description_sources(anime)):
            await callback.answer("Источник описания больше недоступен.", show_alert=True)
            return

        await callback.answer()
        await common_bot._edit_description_view(
            callback.message,
            token,
            anime,
            source_index=source_index,
            page=int(page_text),
        )

    @dp.callback_query(F.data.startswith("as:"))
    async def source_section_callback_handler(callback: CallbackQuery) -> None:
        data = (callback.data or "").split(":")
        if (
            len(data) != 5
            or data[2] not in common_bot.SOURCE_SELECTABLE_SECTIONS
            or not data[3].isdigit()
            or not data[4].isdigit()
        ):
            await callback.answer("Некорректный источник.", show_alert=True)
            return

        _, token, section, source_index_text, page_text = data
        anime = common_bot.ANIME_SESSIONS.get(token)
        if anime is None:
            await callback.answer(
                "Карточка устарела. Выполни поиск ещё раз.",
                show_alert=True,
            )
            return
        if callback.message is None:
            await callback.answer()
            return

        sources = common_bot._source_section_sources(anime, section)
        source_index = int(source_index_text)
        if source_index >= len(sources):
            await callback.answer("Источник больше недоступен.", show_alert=True)
            return

        await callback.answer()
        await common_bot._edit_source_section_view(
            callback.message,
            token,
            anime,
            section,
            source_index,
            int(page_text),
        )

    @dp.callback_query(F.data.startswith("av:"))
    async def anime_view_callback_handler(callback: CallbackQuery) -> None:
        data = (callback.data or "").split(":")
        if len(data) != 4 or not data[3].isdigit():
            await callback.answer("Некорректная команда.", show_alert=True)
            return

        _, token, section, page_text = data
        anime = common_bot.ANIME_SESSIONS.get(token)
        if anime is None:
            await callback.answer(
                "Карточка устарела. Выполни поиск ещё раз.",
                show_alert=True,
            )
            return
        if section not in common_bot.SECTION_LABELS:
            await callback.answer("Некорректный раздел.", show_alert=True)
            return
        if callback.message is None:
            await callback.answer()
            return

        await callback.answer()
        await common_bot._edit_anime_view(
            callback.message,
            token,
            anime,
            section=section,
            page=int(page_text),
        )

    return dp
