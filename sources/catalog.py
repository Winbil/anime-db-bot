from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, cast

from core.capabilities import SourceCapability, SourceDescriptor
from core.contracts import (
    AnimeEpisodeSource,
    AnimeSearchProvider,
    AnimeSource,
    AnimeTrailerSource,
)
from core.settings import SourceSettings, get_settings
from core.source_keys import SourceKey, normalize_source_key
from core.source_names import MAL_SOURCE_NAME
from search.providers.anilist import AniListSearchProvider
from search.providers.mal import MALSearchProvider
from search.providers.shikimori import ShikimoriSearchProvider
from services.source_health import SourceHealthRegistry
from sources.anidb import AniDBSource
from sources.anilist import AniListSource
from sources.jikan import JikanSource
from sources.mal import MALSource
from sources.rate_limited import rate_limited_source
from sources.resilient import (
    resilient_episode_source,
    resilient_search_provider,
    resilient_source,
    resilient_trailer_source,
)
from sources.shikimori import ShikimoriSource
from sources.trailers import AniListTrailerSource, ShikimoriTrailerSource

SearchFactory = Callable[[SourceSettings], AnimeSearchProvider]
MetadataFactory = Callable[[SourceSettings], AnimeSource]
BackendFactory = Callable[[SourceSettings], Any]
EnabledPredicate = Callable[[SourceSettings], bool]


def _always_enabled(settings: SourceSettings) -> bool:
    del settings
    return True


@dataclass(frozen=True, slots=True)
class BackendRegistration:
    order: int
    factory: BackendFactory
    enabled: EnabledPredicate = _always_enabled


@dataclass(frozen=True, slots=True)
class SourceRegistration:
    descriptor: SourceDescriptor
    search_factory: SearchFactory | None = None
    metadata_factory: MetadataFactory | None = None
    metadata_enabled: EnabledPredicate = _always_enabled
    trailer_backends: tuple[BackendRegistration, ...] = ()
    episode_backends: tuple[BackendRegistration, ...] = ()

    @property
    def key(self) -> SourceKey:
        return self.descriptor.key

    @property
    def display_name(self) -> str:
        return self.descriptor.display_name

    @property
    def capabilities(self) -> frozenset[SourceCapability]:
        return self.descriptor.capabilities

    @property
    def optional(self) -> bool:
        return self.descriptor.optional

    def supports(self, capability: SourceCapability) -> bool:
        return self.descriptor.supports(capability)


def _descriptor(
    key: SourceKey,
    display_name: str,
    *capabilities: SourceCapability,
    optional: bool = False,
) -> SourceDescriptor:
    return SourceDescriptor(
        key=key,
        display_name=display_name,
        capabilities=frozenset(capabilities),
        optional=optional,
    )


SOURCE_CATALOG: tuple[SourceRegistration, ...] = (
    SourceRegistration(
        descriptor=_descriptor(
            SourceKey.SHIKIMORI,
            "Shikimori",
            SourceCapability.SEARCH,
            SourceCapability.METADATA,
            SourceCapability.PEOPLE,
            SourceCapability.CHARACTERS,
            SourceCapability.TRAILERS,
        ),
        search_factory=ShikimoriSearchProvider,
        metadata_factory=ShikimoriSource,
        trailer_backends=(BackendRegistration(10, ShikimoriTrailerSource),),
    ),
    SourceRegistration(
        descriptor=_descriptor(
            SourceKey.MAL,
            MAL_SOURCE_NAME,
            SourceCapability.SEARCH,
            SourceCapability.METADATA,
            SourceCapability.PEOPLE,
            SourceCapability.CHARACTERS,
            SourceCapability.TRAILERS,
            SourceCapability.EPISODES,
        ),
        search_factory=MALSearchProvider,
        metadata_factory=MALSource,
        trailer_backends=(BackendRegistration(30, JikanSource),),
        episode_backends=(BackendRegistration(10, JikanSource),),
    ),
    SourceRegistration(
        descriptor=_descriptor(
            SourceKey.ANILIST,
            "AniList",
            SourceCapability.SEARCH,
            SourceCapability.METADATA,
            SourceCapability.PEOPLE,
            SourceCapability.CHARACTERS,
            SourceCapability.TRAILERS,
        ),
        search_factory=AniListSearchProvider,
        metadata_factory=AniListSource,
        trailer_backends=(BackendRegistration(20, AniListTrailerSource),),
    ),
    SourceRegistration(
        descriptor=_descriptor(
            SourceKey.ANIDB,
            "AniDB",
            SourceCapability.METADATA,
            SourceCapability.PEOPLE,
            SourceCapability.CHARACTERS,
            SourceCapability.EPISODES,
            optional=True,
        ),
        metadata_factory=AniDBSource,
        metadata_enabled=AniDBSource.is_enabled,
        episode_backends=(
            BackendRegistration(20, AniDBSource, enabled=AniDBSource.is_enabled),
        ),
    ),
)

SOURCE_REGISTRATIONS: dict[SourceKey, SourceRegistration] = {
    registration.key: registration for registration in SOURCE_CATALOG
}


def registration_for(key: SourceKey | str) -> SourceRegistration:
    return SOURCE_REGISTRATIONS[normalize_source_key(key)]


def descriptor_for(key: SourceKey | str) -> SourceDescriptor:
    return registration_for(key).descriptor


def source_supports(key: SourceKey | str, capability: SourceCapability) -> bool:
    return registration_for(key).supports(capability)


def source_keys_with(capability: SourceCapability) -> tuple[SourceKey, ...]:
    return tuple(
        registration.key
        for registration in SOURCE_CATALOG
        if registration.supports(capability)
    )


def source_key_for_display_name(display_name: str) -> SourceKey | None:
    normalized = " ".join((display_name or "").split()).strip().casefold()
    for registration in SOURCE_CATALOG:
        if registration.display_name.casefold() == normalized:
            return registration.key
    return None


def get_search_provider_map(
    settings: SourceSettings | None = None,
    health: SourceHealthRegistry | None = None,
) -> dict[SourceKey, AnimeSearchProvider]:
    settings = settings or get_settings().sources
    result: dict[SourceKey, AnimeSearchProvider] = {}
    for registration in SOURCE_CATALOG:
        factory = registration.search_factory
        if factory is None or not registration.supports(SourceCapability.SEARCH):
            continue
        provider = resilient_search_provider(
            factory(settings),
            health,
            health_key=registration.key.value,
        )
        result[registration.key] = cast(AnimeSearchProvider, provider)
    return result


def get_search_providers(
    settings: SourceSettings | None = None,
    health: SourceHealthRegistry | None = None,
) -> tuple[AnimeSearchProvider, ...]:
    providers = get_search_provider_map(settings, health)
    return tuple(
        providers[registration.key]
        for registration in SOURCE_CATALOG
        if registration.key in providers
    )


def get_source_map(
    health: SourceHealthRegistry | None = None,
    settings: SourceSettings | None = None,
) -> dict[SourceKey, AnimeSource]:
    settings = settings or get_settings().sources
    result: dict[SourceKey, AnimeSource] = {}
    for registration in SOURCE_CATALOG:
        factory = registration.metadata_factory
        if (
            factory is None
            or not registration.supports(SourceCapability.METADATA)
            or not registration.metadata_enabled(settings)
        ):
            continue
        source = resilient_source(
            rate_limited_source(factory(settings), registration.key.value),
            health,
        )
        source.source_key = registration.key
        result[registration.key] = cast(AnimeSource, source)
    return result


def get_sources(
    health: SourceHealthRegistry | None = None,
    settings: SourceSettings | None = None,
) -> tuple[AnimeSource, ...]:
    return tuple(get_source_map(health, settings).values())


def _build_backends(
    attribute: str,
    settings: SourceSettings,
) -> list[Any]:
    registrations: list[tuple[int, BackendRegistration]] = []
    for source in SOURCE_CATALOG:
        for backend in cast(
            tuple[BackendRegistration, ...],
            getattr(source, attribute),
        ):
            if backend.enabled(settings):
                registrations.append((backend.order, backend))
    registrations.sort(key=lambda item: item[0])
    return [backend.factory(settings) for _, backend in registrations]


def get_trailer_sources(
    settings: SourceSettings | None = None,
    health: SourceHealthRegistry | None = None,
) -> tuple[AnimeTrailerSource, ...]:
    settings = settings or get_settings().sources
    return tuple(
        cast(AnimeTrailerSource, resilient_trailer_source(source, health))
        for source in _build_backends("trailer_backends", settings)
    )


def get_episode_sources(
    settings: SourceSettings | None = None,
    health: SourceHealthRegistry | None = None,
) -> tuple[AnimeEpisodeSource, ...]:
    settings = settings or get_settings().sources
    return tuple(
        cast(AnimeEpisodeSource, resilient_episode_source(source, health))
        for source in _build_backends("episode_backends", settings)
    )
