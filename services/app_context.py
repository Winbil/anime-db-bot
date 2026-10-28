from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass
from typing import Iterator

from core.contracts import AnimeSearchProvider, AnimeSource
from core.settings import AppSettings, get_settings
from search.registry import get_search_providers
from services.characters import CharacterService
from services.direct_lookup import DirectIdLookupService
from services.episodes import EpisodeService
from services.identity_aggregator import AnimeAggregator
from services.search import SearchService
from services.trailers import TrailerService
from sources.episode_registry import get_episode_sources
from sources.registry import get_sources
from sources.trailer_registry import get_trailer_sources


@dataclass(slots=True)
class AppContext:
    """Application composition root shared by transport/UI adapters.

    Construction happens explicitly at startup. Importing a Telegram UI module no
    longer creates API sources, services or caches as a side effect.
    """

    settings: AppSettings
    search_providers: tuple[AnimeSearchProvider, ...]
    sources: tuple[AnimeSource, ...]
    search_service: SearchService
    aggregator: AnimeAggregator
    character_service: CharacterService
    episode_service: EpisodeService
    trailer_service: TrailerService
    direct_lookup: DirectIdLookupService

    @classmethod
    def create(cls, settings: AppSettings | None = None) -> "AppContext":
        settings = settings or get_settings()
        search_providers = get_search_providers()
        sources = get_sources()
        return cls(
            settings=settings,
            search_providers=search_providers,
            sources=sources,
            search_service=SearchService(search_providers),
            aggregator=AnimeAggregator(sources),
            character_service=CharacterService(sources),
            episode_service=EpisodeService(get_episode_sources()),
            trailer_service=TrailerService(get_trailer_sources()),
            direct_lookup=DirectIdLookupService(sources),
        )

    async def aclose(self) -> None:
        """Close owned resources when implementations expose async lifecycle."""
        seen: set[int] = set()
        resources = [
            *self.sources,
            *self.episode_service.sources,
            *self.trailer_service.sources,
        ]
        for resource in resources:
            if id(resource) in seen:
                continue
            seen.add(id(resource))
            close = getattr(resource, "aclose", None)
            if callable(close):
                await close()


_CURRENT_CONTEXT: ContextVar[AppContext | None] = ContextVar(
    "anime_db_bot_app_context",
    default=None,
)


def get_app_context() -> AppContext:
    context = _CURRENT_CONTEXT.get()
    if context is None:
        raise RuntimeError(
            "AppContext is not active. Build it at the application entrypoint and "
            "activate it before dispatching handlers."
        )
    return context


@contextmanager
def activate_app_context(context: AppContext) -> Iterator[AppContext]:
    token: Token[AppContext | None] = _CURRENT_CONTEXT.set(context)
    try:
        yield context
    finally:
        _CURRENT_CONTEXT.reset(token)
