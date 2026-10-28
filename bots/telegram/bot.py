from __future__ import annotations

import asyncio
import logging

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message

from bots.telegram.admin import TelegramModerationMiddleware, register_admin_handlers
from bots.telegram.card.handlers import build_dispatcher
from bots.telegram.card.service import aggregate_and_send
from bots.telegram.people_portraits import handle_people_callback
from bots.telegram.rate_limit import TelegramRateLimitMiddleware
from bots.telegram.search_ui import register_search_handlers
from bots.telegram.transports import TelegramTransport
from bots.telegram.transports.official import OfficialTelegramTransport
from bots.telegram.transports.tgapi import LocalTelegramTransport
from core.logging_config import configure_logging
from core.models import SearchCandidate
from core.settings import AppSettings, TelegramSettings, get_settings
from localization import text
from mappings.runtime import periodic_mapping_updates
from services.access_control import telegram_admin_ids
from services.app_context import AppContext, activate_app_context
from services.user_settings import get_user_locale


def select_transport(settings: TelegramSettings | None = None) -> TelegramTransport:
    """Select official Telegram API or local tg-bot-api from frozen configuration."""
    settings = settings or get_settings().telegram
    if settings.bot_api_url:
        return LocalTelegramTransport(settings)
    return OfficialTelegramTransport(settings)


async def _aggregate_and_cleanup_search(
    message: Message,
    candidate: SearchCandidate,
    owner_user_id: int,
) -> None:
    """Replace/remove a bot-authored search preview around card aggregation."""
    locale = get_user_locale(owner_user_id)
    is_bot_search_message = bool(message.from_user and message.from_user.is_bot)

    if is_bot_search_message:
        try:
            await message.edit_text(
                text("search", "loading", locale=locale, title=candidate.title),
                reply_markup=None,
            )
        except Exception:
            logging.debug(
                "Could not replace search preview with loading state",
                exc_info=True,
            )

    await aggregate_and_send(message, candidate, owner_user_id)

    if not is_bot_search_message:
        return

    try:
        await message.delete()
        return
    except Exception:
        logging.debug("Could not delete completed search message", exc_info=True)

    try:
        await message.edit_text(
            text("search", "selected", locale=locale, title=candidate.title),
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
            if await handle_people_callback(event):
                return None
        return await handler(event, data)


async def run_bot(
    transport: TelegramTransport | None = None,
    *,
    context: AppContext | None = None,
) -> None:
    """Build and run the Telegram implementation of anime-db-bot."""
    settings = context.settings if context is not None else get_settings()
    settings.require_bot_token()
    configure_logging(
        level=settings.logging.level,
        structured=settings.logging.structured,
        secrets=(
            settings.telegram.bot_token,
            settings.sources.anilist_access_token,
            settings.sources.mal_client_id,
        ),
    )
    context = context or AppContext.create(settings)
    transport = transport or select_transport(settings.telegram)

    logging.info("Bot platform: Telegram")
    logging.info("Telegram transport: %s", transport.mode_name)
    logging.info("Configured Telegram administrators: %d", len(telegram_admin_ids()))
    logging.info(
        "Personal rate limit: %d/min/user, %d/hour/user (admins bypass personal limit)",
        context.personal_rate_limiter.per_minute,
        context.personal_rate_limiter.per_hour,
    )
    logging.info("Default search providers: %s", context.search_service.provider_name)
    logging.info(
        "Metadata sources: %s", ", ".join(source.name for source in context.sources)
    )
    logging.info(
        "Interactive /anime provider selection and direct-ID lookup are enabled"
    )

    bot = transport.create_bot()
    mapping_task = asyncio.create_task(periodic_mapping_updates())
    try:
        with activate_app_context(context):
            health = await transport.check_health(bot)
            if health.healthy:
                identity = f" @{health.bot_username}" if health.bot_username else ""
                logging.info(
                    "Telegram transport health: healthy%s — %s", identity, health.detail
                )
            else:
                logging.warning(
                    "Telegram transport health: degraded — %s", health.detail
                )

            dp = build_dispatcher(mode_name=transport.mode_name)
            moderation = TelegramModerationMiddleware()
            rate_limit = TelegramRateLimitMiddleware(context.personal_rate_limiter)
            dp.message.outer_middleware(moderation)
            dp.message.outer_middleware(rate_limit)
            dp.callback_query.outer_middleware(moderation)
            dp.callback_query.outer_middleware(rate_limit)
            dp.callback_query.outer_middleware(_CallbackRoutingMiddleware())

            register_admin_handlers(dp)
            register_search_handlers(
                dp,
                aggregate_callback=_aggregate_and_cleanup_search,
                default_service=context.search_service,
                direct_lookup=context.direct_lookup,
                provider_map=context.search_provider_map,
            )

            await dp.start_polling(bot)
    finally:
        mapping_task.cancel()
        await asyncio.gather(mapping_task, return_exceptions=True)
        await transport.close(bot)
        await context.aclose()


def main() -> None:
    asyncio.run(run_bot())


if __name__ == "__main__":
    main()
