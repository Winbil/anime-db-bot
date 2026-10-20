from __future__ import annotations

from core.contracts import AnimeSource
from sources.anilist import AniListSource
from sources.mal import MALSource
from sources.shikimori_people import ShikimoriSource


def get_sources() -> tuple[AnimeSource, ...]:
    """Composition point for enabled metadata-source adapters."""
    return (
        ShikimoriSource(),
        AniListSource(),
        MALSource(),
    )
