from __future__ import annotations

import asyncio
import logging
import time

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message

from bots.telegram.admin import TelegramModerationMiddleware, register_admin_handlers
from bots.telegram.card.runtime.handlers import build_dispatcher
from bots.telegram.card.runtime.service import aggregate_and_send
from bots.telegram.card.runtime.state import TelegramCardState
from bots.telegram.people.portraits import handle_people_callback
from bots.telegram.rate_limit import TelegramRateLimitMiddleware
from bots.telegram.search.handlers import register_search_handlers
from bots.telegram.transports import TelegramTransport
from bots.telegram.transports.official import OfficialTelegramTransport
from bots.telegram.transports.tgapi import LocalTelegramTransport
from core.logging_config import configure_logging
from core.models import SearchCandidate
from core.observability import bind_observability_context, new_correlation_id
from core.proxy_config import ProxyProfile, load_proxy_settings
from core.settings import TelegramSettings, get_settings
from core.user_agent_config import UserAgentProfile, load_user_agent_settings
from localization import text
from mappings.runtime import periodic_mapping_updates
from services.users.access_control import telegram_admin_ids
from services.runtime.app_context import AppContext, activate_app_context
from services.users.settings import get_user_locale


def select_transport(
    settings: TelegramSettings | None = None,
    proxy_profile: ProxyProfile | None = None,
    user_agent_profile: UserAgentProfile | None = None,
) -> TelegramTransport:
    """Select Telegram API backend with independent proxy/User-Agent profiles."""
    settings = settings or get_settings().telegram
    proxy_profile = proxy_profile or load_proxy_settings().profile("telegram")
    user_agent_profile = user_agent_profile or load_user_agent_settings().profile(
        "telegram"
    )
    # Custom Telegram routing must reach the real external API, not only the
    # loopback hop to a shared/self-hosted telegram-bot-api instance.
    if proxy_profile.active or user_agent_profile.preferred:
        return OfficialTelegramTransport(settings, proxy_profile, user_agent_profile)
    if settings.bot_api_url:
        return LocalTelegramTransport(settings, proxy_profile, user_agent_profile)
    return OfficialTelegramTransport(settings, proxy_profile, user_agent_profile)


async def _aggregate_and_cleanup_search(
    message: Message,
    candidate: SearchCandidate,
    owner_user_id: int,
    card_state: TelegramCardState,
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

    await aggregate_and_send(message, candidate, owner_user_id, card_state)

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


def _update_action(event: object) -> str:
    if isinstance(event, CallbackQuery):
        return "callback"
    if isinstance(event, Message):
        text_value = event.text or event.caption or ""
        return "command" if text_value.lstrip().startswith("/") else "message"
    return "update"


class _ObservabilityMiddleware(BaseMiddleware):
    """Attach one privacy-safe correlation context to each Telegram update."""

    async def __call__(self, handler, event, data):
        started = time.monotonic()
        with bind_observability_context(
            correlation_id=new_correlation_id(),
            platform="telegram",
            action=_update_action(event),
        ):
            logging.info(
                "Telegram update started",
                extra={"event": "telegram_update", "outcome": "started"},
            )
            try:
                result = await handler(event, data)
            except Exception as exc:
                logging.error(
                    "Telegram update failed",
                    extra={
                        "event": "telegram_update",
                        "outcome": "error",
                        "error_type": type(exc).__name__,
                        "duration_ms": round((time.monotonic() - started) * 1000, 3),
                    },
                )
                raise
            logging.info(
                "Telegram update completed",
                extra={
                    "event": "telegram_update",
                    "outcome": "success",
                    "duration_ms": round((time.monotonic() - started) * 1000, 3),
                },
            )
            return result


class _CallbackRoutingMiddleware(BaseMiddleware):
    """Route callback extensions that sit outside the core card handlers."""

    def __init__(self, card_state: TelegramCardState) -> None:
        self._card_state = card_state

    async def __call__(self, handler, event, data):
        if isinstance(event, CallbackQuery) and await handle_people_callback(
            event, self._card_state
        ):
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
    context = context or AppContext.create(settings)
    configure_logging(
        level=settings.logging.level,
        structured=settings.logging.structured,
        redact_secrets=settings.logging.redact_secrets,
        log_directory=settings.logging.directory,
        log_max_bytes=settings.logging.max_bytes,
        log_backups=settings.logging.backups,
        secrets=(
            settings.telegram.bot_token,
            settings.sources.anilist_access_token,
            settings.sources.mal_client_id,
            settings.sources.trace_moe_api_key,
            settings.sources.whatanimeisthis_api_key,
            *context.proxy_settings.secret_values(),
        ),
    )
    transport = transport or select_transport(
        settings.telegram,
        context.proxy_settings.profile("telegram"),
        context.user_agent_settings.profile("telegram"),
    )

    if not settings.logging.redact_secrets:
        logging.warning(
            "Log secret redaction is disabled; sensitive values may be written verbatim",
            extra={
                "event": "logging_config",
                "outcome": "redaction_disabled",
            },
        )

    logging.info("Bot platform: Telegram")
    logging.info("Telegram transport: %s", transport.mode_name)
    logging.info(
        "Telegram proxy route: %s",
        f"{len(transport.proxy_profile.active)} enabled proxy entries"
        if transport.proxy_profile.active
        else "direct",
    )
    preferred_user_agents = transport.user_agent_profile.preferred
    logging.info(
        "Telegram User-Agent route: %s",
        ", ".join(entry.name for entry in preferred_user_agents)
        if preferred_user_agents
        else "anime-db-bot default",
    )
    proxied_sources = [
        name
        for name in context.proxy_settings.profiles
        if name != "telegram" and context.proxy_settings.active(name)
    ]
    logging.info(
        "Source proxy profiles enabled: %s",
        ", ".join(proxied_sources) if proxied_sources else "none",
    )
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
    card_state = TelegramCardState.create(settings.telegram.session_ttl_seconds)
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

            dp = build_dispatcher(mode_name=transport.mode_name, state=card_state)
            observability = _ObservabilityMiddleware()
            moderation = TelegramModerationMiddleware()
            rate_limit = TelegramRateLimitMiddleware(context.personal_rate_limiter)
            dp.message.outer_middleware(observability)
            dp.message.outer_middleware(moderation)
            dp.message.outer_middleware(rate_limit)
            dp.callback_query.outer_middleware(observability)
            dp.callback_query.outer_middleware(moderation)
            dp.callback_query.outer_middleware(rate_limit)
            dp.callback_query.outer_middleware(_CallbackRoutingMiddleware(card_state))

            register_admin_handlers(dp, source_health=context.source_health)

            async def aggregate_search_result(
                message: Message,
                candidate: SearchCandidate,
                owner_user_id: int,
            ) -> None:
                await _aggregate_and_cleanup_search(
                    message,
                    candidate,
                    owner_user_id,
                    card_state,
                )

            register_search_handlers(
                dp,
                aggregate_callback=aggregate_search_result,
                default_service=context.search_service,
                direct_lookup=context.direct_lookup,
                provider_map=context.search_provider_map,
                image_search_service=context.image_search_service,
                image_search_max_bytes=context.settings.sources.image_search_max_bytes,
                input_ttl_seconds=context.settings.telegram.anime_input_ttl_seconds,
                telegram_local_file_root=context.settings.telegram.bot_api_local_file_root,
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
