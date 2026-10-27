from __future__ import annotations

import logging

from aiogram.types import Message

from bots.telegram.card.renderer import send_anime_view
from bots.telegram.card.state import remember_anime
from core.models import SearchCandidate
from localization import text
from search.registry import get_search_providers
from services.episodes import EpisodeService
from services.identity_aggregator import AnimeAggregator
from services.search import SearchService
from services.trailers import TrailerService
from services.user_settings import get_user_locale
from sources.episode_registry import get_episode_sources
from sources.registry import get_sources
from sources.trailer_registry import get_trailer_sources

SEARCH_PROVIDERS = get_search_providers()
SOURCES = get_sources()
SEARCH_SERVICE = SearchService(SEARCH_PROVIDERS)
AGGREGATOR = AnimeAggregator(SOURCES)
EPISODE_SERVICE = EpisodeService(get_episode_sources())
TRAILER_SERVICE = TrailerService(get_trailer_sources())


async def aggregate_and_send(
    message: Message,
    candidate: SearchCandidate,
    owner_user_id: int,
) -> None:
    locale = get_user_locale(owner_user_id)
    identity = candidate.identity
    if identity.is_empty():
        await message.answer(text("search", "result_unavailable", locale=locale))
        return

    try:
        anime = await AGGREGATOR.aggregate(candidate)
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

    token = remember_anime(anime, owner_user_id)
    await send_anime_view(
        message,
        token,
        anime,
        section="main",
        page=0,
        locale=locale,
    )
