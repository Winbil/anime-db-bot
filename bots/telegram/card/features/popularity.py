from __future__ import annotations

import logging

from aiogram.types import Message

from bots.telegram.card.runtime.state import AnimeCardSession
from localization import text
from services.runtime.app_context import get_app_context


async def ensure_popularity_loaded(
    message: Message,
    session: AnimeCardSession,
    *,
    locale: str,
) -> None:
    if session.popularity_loaded:
        return
    try:
        await message.edit_text(
            text=text("card", "popularity_loading", locale=locale),
            reply_markup=None,
        )
    except Exception:
        logging.debug("Could not show popularity loading state", exc_info=True)

    result = await get_app_context().popularity_service.load(session.anime.identity)
    session.anime.popularity_by_source = result.by_source
    session.popularity_errors = result.errors
    session.popularity_loaded = True
