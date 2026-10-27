from __future__ import annotations

from core.contracts import AnimeTrailerSource
from sources.trailers import get_builtin_trailer_sources


def get_trailer_sources() -> tuple[AnimeTrailerSource, ...]:
    """Return lazy trailer providers in deterministic UI order."""
    return tuple(get_builtin_trailer_sources())
