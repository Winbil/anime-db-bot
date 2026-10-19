from __future__ import annotations

from sources.base import AnimeSource
from sources.shikimori import ShikimoriSource


def get_sources() -> tuple[AnimeSource, ...]:
    """Return enabled source adapters. Search and bot code never import them directly."""
    return (ShikimoriSource(),)
