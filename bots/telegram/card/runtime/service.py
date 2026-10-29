from __future__ import annotations

import logging

from aiogram.types import Message

from bots.telegram.card.views.renderer import send_anime_view
from bots.telegram.card.runtime.state import TelegramCardState
from core.models import SearchCandidate
from localization import text
from services.runtime.app_context import get_app_context
from services.users.settings import get_user_locale


async def aggregate_and_send(
    message: Message,
    candidate: SearchCandidate,
    owner_user_id: int,
    state: TelegramCardState,
) -> None:
    locale = get_user_locale(owner_user_id)
    identity = candidate.identity
    if identity.is_empty():
        await message.answer(text("search", "result_unavailable", locale=locale))
        return

    try:
        anime = await get_app_context().aggregator.aggregate(candidate)
    except Exception as exc:
        logging.error(
            "Anime aggregation failed for %s: %s: %s",
            identity.describe(),
            type(exc).__name__,
            exc,
            exc_info=True,
        )
        await message.answer(text("search", "get_result_failed", locale=locale))
        return

    token = state.remember_anime(anime, owner_user_id)
    await send_anime_view(
        message,
        token,
        anime,
        section="main",
        page=0,
        locale=locale,
    )
