from __future__ import annotations

import logging

from aiogram.types import Message

from bots.telegram.card.renderer import send_anime_view
from bots.telegram.card.state import remember_anime
from core.models import SearchCandidate
from localization import text
from search.registry import get_search_providers
from services.aggregator import AnimeAggregator
from services.search import SearchService
from services.user_settings import get_user_locale
from sources.registry import get_sources

SEARCH_PROVIDERS = get_search_providers()
SOURCES = get_sources()
SEARCH_SERVICE = SearchService(SEARCH_PROVIDERS)
AGGREGATOR = AnimeAggregator(SOURCES)


async def aggregate_and_send(
    message: Message,
    candidate: SearchCandidate,
    owner_user_id: int,
) -> None:
    locale = get_user_locale(owner_user_id)
    mal_id = candidate.external_ids.get("mal")
    if not mal_id:
        await message.answer(text("service", "missing_mal_id", locale=locale))
        return

    try:
        anime = await AGGREGATOR.aggregate(candidate)
    except Exception as exc:
        logging.error(
            "Anime aggregation failed for MAL %s: %s: %s",
            mal_id,
            type(exc).__name__,
            exc,
            exc_info=True,
        )
        await message.answer(
            text("service", "aggregation_failed", locale=locale, mal_id=mal_id)
        )
        return

    token = remember_anime(anime, owner_user_id)
    await send_anime_view(
        message,
        token,
        anime,
        section="main",
        page=0,
        locale=locale,
    )
