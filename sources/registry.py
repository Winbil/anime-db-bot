from __future__ import annotations

from core.contracts import AnimeSource
from sources.identity_sources import AniListIdentitySource, ShikimoriIdentitySource
from sources.mal import MALSource
from sources.resilient import resilient_source


def get_sources() -> tuple[AnimeSource, ...]:
    """Composition point for enabled identity-native metadata sources."""
    return tuple(
        resilient_source(source)
        for source in (
            ShikimoriIdentitySource(),
            AniListIdentitySource(),
            MALSource(),
        )
    )
