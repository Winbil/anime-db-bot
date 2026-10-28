from __future__ import annotations

from collections.abc import Callable

from core.capabilities import SourceCapability, source_keys_with
from core.contracts import AnimeSource
from core.settings import SourceSettings, get_settings
from core.source_keys import SourceKey
from services.source_health import SourceHealthRegistry
from sources.anidb import AniDBSource
from sources.anilist import AniListSource
from sources.shikimori import ShikimoriSource
from sources.mal import MALSource
from sources.rate_limited import rate_limited_source
from sources.resilient import resilient_source


_SOURCE_FACTORIES: dict[SourceKey, Callable[[SourceSettings], AnimeSource]] = {
    SourceKey.SHIKIMORI: ShikimoriSource,
    SourceKey.ANILIST: AniListSource,
    SourceKey.MAL: MALSource,
    SourceKey.ANIDB: AniDBSource,
}


def get_source_map(
    health: SourceHealthRegistry | None = None,
    settings: SourceSettings | None = None,
) -> dict[SourceKey, AnimeSource]:
    """Return enabled metadata sources declared by the capability catalog."""
    settings = settings or get_settings().sources
    result: dict[SourceKey, AnimeSource] = {}
    for source_key in source_keys_with(SourceCapability.METADATA):
        if source_key is SourceKey.ANIDB and not AniDBSource.is_enabled(settings):
            continue
        factory = _SOURCE_FACTORIES.get(source_key)
        if factory is None:
            continue

        # Rate limiting wraps the raw source, then retry/health wraps that proxy.
        # Every retry therefore consumes quota again instead of bypassing the
        # outbound safety limiter.
        source = resilient_source(
            rate_limited_source(factory(settings), source_key.value),
            health,
        )
        source.source_key = source_key
        result[source_key] = source
    return result


def get_sources(
    health: SourceHealthRegistry | None = None,
    settings: SourceSettings | None = None,
) -> tuple[AnimeSource, ...]:
    """Composition point for enabled identity-native metadata sources."""
    return tuple(get_source_map(health, settings).values())
