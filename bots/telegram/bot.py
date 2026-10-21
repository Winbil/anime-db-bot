from __future__ import annotations

import asyncio
import logging
import os

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message
from dotenv import load_dotenv

from bots.telegram import common as common_bot
from bots.telegram.card_handlers import build_dispatcher
from bots.telegram.people_portraits import handle_people_callback
from bots.telegram.search_ui import register_search_handlers
from bots.telegram.transports import TelegramTransport
from bots.telegram.transports.official import TRANSPORT as OFFICIAL_TRANSPORT
from bots.telegram.transports.tgapi import TRANSPORT as TGAPI_TRANSPORT
from core.models import SearchCandidate

load_dotenv()


def select_transport() -> TelegramTransport:
    """Select official Telegram API or local tg-bot-api from configuration."""
    if os.getenv("TELEGRAM_BOT_API_URL", "").strip():
        return TGAPI_TRANSPORT
    return OFFICIAL_TRANSPORT


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

    await common_bot._aggregate_and_send(message, candidate)

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


class _CallbackRoutingMiddleware(BaseMiddleware):
    """Route callback extensions that sit outside the core card handlers."""

    async def __call__(self, handler, event, data):
        if isinstance(event, CallbackQuery):
            if await handle_people_callback(common_bot, event):
                return None
        return await handler(event, data)


async def run_bot(transport: TelegramTransport | None = None) -> None:
    """Build and run the Telegram implementation of anime-db-bot."""
    transport = transport or select_transport()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    logging.info("Bot platform: Telegram")
    logging.info("Telegram transport: %s", transport.mode_name)
    logging.info("Default search providers: %s", common_bot.SEARCH_SERVICE.provider_name)
    logging.info("Metadata sources: %s", ", ".join(source.name for source in common_bot.SOURCES))
    logging.info("Selectable /search providers are enabled")

    bot = transport.create_bot()
    try:
        health = await transport.check_health(bot)
        if health.healthy:
            identity = f" @{health.bot_username}" if health.bot_username else ""
            logging.info("Telegram transport health: healthy%s — %s", identity, health.detail)
        else:
            logging.warning("Telegram transport health: degraded — %s", health.detail)

        dp = build_dispatcher(mode_name=transport.mode_name)
        dp.callback_query.outer_middleware(_CallbackRoutingMiddleware())

        register_search_handlers(
            dp,
            aggregate_callback=_aggregate_and_cleanup_search,
            default_service=common_bot.SEARCH_SERVICE,
        )

        await dp.start_polling(bot)
    finally:
        await transport.close(bot)


def main() -> None:
    asyncio.run(run_bot())


if __name__ == "__main__":
    main()
