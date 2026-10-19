from __future__ import annotations

from core.contracts import AnimeSource
from sources.shikimori import ShikimoriSource


def get_sources() -> tuple[AnimeSource, ...]:
    """Composition point for enabled source adapters."""
    return (ShikimoriSource(),)
