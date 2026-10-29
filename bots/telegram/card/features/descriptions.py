from __future__ import annotations

import logging

from aiogram.types import Message

from bots.telegram.card.runtime.state import AnimeCardSession
from localization import text
from services.runtime.app_context import get_app_context


async def ensure_descriptions_loaded(
    message: Message,
    session: AnimeCardSession,
    *,
    locale: str,
) -> None:
    if session.descriptions_loaded:
        return
    try:
        await message.edit_text(
            text=text("card", "description_loading", locale=locale),
            reply_markup=None,
        )
    except Exception:
        logging.debug("Could not show description loading state", exc_info=True)

    result = await get_app_context().description_service.load(session.anime.identity)
    session.anime.descriptions = {
        source: details.description
        for source, details in result.by_source.items()
        if details.description
    }
    session.anime.backgrounds_by_source = {
        source: details.background
        for source, details in result.by_source.items()
        if details.background
    }
    session.anime.background = next(
        iter(session.anime.backgrounds_by_source.values()), None
    )
    session.description_errors = result.errors
    session.descriptions_loaded = True
