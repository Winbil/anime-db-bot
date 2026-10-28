from __future__ import annotations

from core.contracts import AnimeTrailerSource
from core.settings import SourceSettings
from sources.trailers import get_builtin_trailer_sources


def get_trailer_sources(
    settings: SourceSettings | None = None,
) -> tuple[AnimeTrailerSource, ...]:
    """Return lazy trailer providers in deterministic UI order."""
    return tuple(get_builtin_trailer_sources(settings))
