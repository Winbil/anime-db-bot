from __future__ import annotations

import logging

from aiogram.types import Message

from bots.telegram.card.renderer import send_anime_view
from bots.telegram.card.state import remember_anime
from core.models import SearchCandidate
from search.registry import get_search_providers
from services.aggregator import AnimeAggregator
from services.search import SearchService
from sources.registry import get_sources

SEARCH_PROVIDERS = get_search_providers()
SOURCES = get_sources()
SEARCH_SERVICE = SearchService(SEARCH_PROVIDERS)
AGGREGATOR = AnimeAggregator(SOURCES)


async def aggregate_and_send(message: Message, candidate: SearchCandidate) -> None:
    mal_id = candidate.external_ids.get("mal")
    if not mal_id:
        await message.answer("У выбранного результата нет MAL ID.")
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
            f"Не удалось собрать данные для MAL ID {mal_id} из подключённых источников."
        )
        return

    token = remember_anime(anime)
    await send_anime_view(message, token, anime, section="main", page=0)
