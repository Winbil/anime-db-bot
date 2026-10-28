from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass
from typing import Iterator

from core.contracts import AnimeSearchProvider, AnimeSource
from core.http_client import HttpClientPool, activate_http_pool
from core.settings import AppSettings, get_settings
from core.source_keys import SourceKey
from services.bans import SQLiteBanStore, activate_ban_store
from services.characters import CharacterService
from services.direct_lookup import DirectIdLookupService
from services.episodes import EpisodeService
from services.identity_aggregator import AnimeAggregator
from services.people_progress import PeopleProgressService
from services.rate_limits import (
    PersonalRateLimiter,
    UpstreamRateLimiter,
    activate_rate_limiters,
)
from services.search import SearchService
from services.source_health import SourceHealthRegistry
from services.trailers import TrailerService
from services.user_settings import (
    SQLiteUserSettingsStore,
    activate_user_settings_store,
)
from sources.catalog import (
    get_episode_sources,
    get_search_provider_map,
    get_sources,
    get_trailer_sources,
)


@dataclass(slots=True)
class AppContext:
    """Application composition root shared by transport/UI adapters."""

    settings: AppSettings
    http: HttpClientPool
    source_health: SourceHealthRegistry
    user_settings_store: SQLiteUserSettingsStore
    ban_store: SQLiteBanStore
    personal_rate_limiter: PersonalRateLimiter
    upstream_rate_limiter: UpstreamRateLimiter
    search_provider_map: dict[SourceKey, AnimeSearchProvider]
    search_providers: tuple[AnimeSearchProvider, ...]
    sources: tuple[AnimeSource, ...]
    search_service: SearchService
    aggregator: AnimeAggregator
    character_service: CharacterService
    episode_service: EpisodeService
    trailer_service: TrailerService
    people_progress_service: PeopleProgressService
    direct_lookup: DirectIdLookupService

    @classmethod
    def create(cls, settings: AppSettings | None = None) -> "AppContext":
        settings = settings or get_settings()
        http = HttpClientPool()
        source_health = SourceHealthRegistry(
            failure_threshold=settings.source_health.failure_threshold,
            cooldown_seconds=settings.source_health.cooldown_seconds,
        )
        user_settings_store = SQLiteUserSettingsStore(
            settings.storage.user_settings_db_path
        )
        ban_store = SQLiteBanStore(settings.storage.bans_db_path)
        personal_rate_limiter = PersonalRateLimiter(settings.rate_limits)
        upstream_rate_limiter = UpstreamRateLimiter(settings.rate_limits)
        search_provider_map = get_search_provider_map(settings.sources)
        search_providers = tuple(search_provider_map.values())
        sources = get_sources(source_health, settings.sources)
        aggregator = AnimeAggregator(sources)
        return cls(
            settings=settings,
            http=http,
            source_health=source_health,
            user_settings_store=user_settings_store,
            ban_store=ban_store,
            personal_rate_limiter=personal_rate_limiter,
            upstream_rate_limiter=upstream_rate_limiter,
            search_provider_map=search_provider_map,
            search_providers=search_providers,
            sources=sources,
            search_service=SearchService(search_providers, settings=settings.search),
            aggregator=aggregator,
            character_service=CharacterService(sources),
            episode_service=EpisodeService(get_episode_sources(settings.sources)),
            trailer_service=TrailerService(get_trailer_sources(settings.sources)),
            people_progress_service=PeopleProgressService(
                sources,
                aggregator,
                portrait_batch_size=settings.sources.people_portrait_batch_size,
            ),
            direct_lookup=DirectIdLookupService(sources),
        )

    async def aclose(self) -> None:
        """Close owned runtime resources exactly once where possible."""
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
        await self.http.aclose()


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
        with (
            activate_http_pool(context.http),
            activate_user_settings_store(context.user_settings_store),
            activate_ban_store(context.ban_store),
            activate_rate_limiters(
                context.personal_rate_limiter,
                context.upstream_rate_limiter,
            ),
        ):
            yield context
    finally:
        _CURRENT_CONTEXT.reset(token)
