from __future__ import annotations

import logging

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message

from bots import common as common_bot
from bots.people_portraits import handle_people_callback
from bots.search_ui import register_search_handlers
from core.models import SearchCandidate


_RAW_AGGREGATE_AND_SEND = common_bot._aggregate_and_send


async def _aggregate_and_cleanup_search(
    message: Message,
    candidate: SearchCandidate,
) -> None:
    """Replace/remove a bot-authored search list around metadata aggregation."""
    is_bot_search_message = bool(message.from_user and message.from_user.is_bot)

    if is_bot_search_message:
        try:
            await message.edit_text(
                f"Загружаю данные для «{candidate.title}»…",
                reply_markup=None,
            )
        except Exception:
            logging.debug(
                "Could not replace search results with loading state",
                exc_info=True,
            )

    # Cross-ID enrichment belongs to AnimeAggregator, so every entry path
    # (single result, /anime selection and explicit /search) behaves the same.
    await _RAW_AGGREGATE_AND_SEND(message, candidate)

    if not is_bot_search_message:
        return

    try:
        await message.delete()
        return
    except Exception:
        logging.debug("Could not delete completed search message", exc_info=True)

    try:
        await message.edit_text(
            f"Выбрано: {candidate.title}",
            reply_markup=None,
        )
    except Exception:
        logging.debug(
            "Could not replace completed search message",
            exc_info=True,
        )


async def _handle_default_pick(callback: CallbackQuery) -> bool:
    """Handle the default /anime result-selection callback explicitly."""
    raw = callback.data or ""
    if not raw.startswith("pick:"):
        return False

    parts = raw.split(":")
    if len(parts) != 4 or not parts[2].isdigit() or not parts[3].isdigit():
        await callback.answer("Некорректный результат.", show_alert=True)
        return True

    _, token, page_text, index_text = parts
    session = common_bot.SEARCH_SESSIONS.get(token)
    if session is None:
        await callback.answer(
            "Этот поиск устарел. Выполни /anime ещё раз.",
            show_alert=True,
        )
        return True
    if callback.message is None:
        await callback.answer()
        return True

    try:
        search_page = await common_bot._get_search_page(
            session,
            max(1, int(page_text)),
        )
    except Exception:
        logging.exception("Could not reload default search page for selection")
        await callback.answer("Не удалось получить результат поиска.", show_alert=True)
        return True

    index = int(index_text)
    if index < 0 or index >= len(search_page.items):
        await callback.answer("Результат больше недоступен.", show_alert=True)
        return True

    candidate = search_page.items[index]
    await callback.answer()
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        logging.debug("Could not remove search keyboard", exc_info=True)
    await _aggregate_and_cleanup_search(callback.message, candidate)
    return True


class _CallbackRoutingMiddleware(BaseMiddleware):
    """Explicit extension point for callbacks that augment bots.common UI."""

    async def __call__(self, handler, event, data):
        if isinstance(event, CallbackQuery):
            if await handle_people_callback(common_bot, event):
                return None
            if await _handle_default_pick(event):
                return None
        return await handler(event, data)


async def run_bot(*, use_custom_api: bool, mode_name: str) -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    logging.info("Bot mode: %s", mode_name)
    logging.info("Default search providers: %s", common_bot.SEARCH_SERVICE.provider_name)
    logging.info("Metadata sources: %s", ", ".join(source.name for source in common_bot.SOURCES))
    logging.info("Selectable /search providers are enabled")

    bot = common_bot.create_bot(use_custom_api=use_custom_api)
    dp = common_bot.build_dispatcher(mode_name=mode_name)

    dp.callback_query.outer_middleware(_CallbackRoutingMiddleware())

    register_search_handlers(
        dp,
        aggregate_callback=_aggregate_and_cleanup_search,
        default_service=common_bot.SEARCH_SERVICE,
    )

    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()
