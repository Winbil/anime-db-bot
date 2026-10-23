from __future__ import annotations

from collections.abc import Callable

from core.contracts import AnimeSource
from sources.identity_sources import AniListIdentitySource, ShikimoriIdentitySource
from sources.mal import MALSource
from sources.resilient import resilient_source


_SOURCE_FACTORIES: tuple[tuple[str, Callable[[], AnimeSource]], ...] = (
    ("shikimori", ShikimoriIdentitySource),
    ("anilist", AniListIdentitySource),
    ("mal", MALSource),
)


def get_source_map() -> dict[str, AnimeSource]:
    """Return enabled metadata sources keyed by their AnimeIdentity key."""
    result: dict[str, AnimeSource] = {}
    for source_key, factory in _SOURCE_FACTORIES:
        source = resilient_source(factory())
        # RetryingSourceProxy deliberately allows capability attributes supplied
        # by the composition root. New databases only need one registry entry.
        source.source_key = source_key
        result[source_key] = source
    return result


def get_sources() -> tuple[AnimeSource, ...]:
    """Composition point for enabled identity-native metadata sources."""
    return tuple(get_source_map().values())
