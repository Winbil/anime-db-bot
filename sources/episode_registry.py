from __future__ import annotations

from core.contracts import AnimeEpisodeSource
from sources.jikan import JikanSource


def get_episode_sources() -> tuple[AnimeEpisodeSource, ...]:
    """Return registered lazy episode backends.

    Jikan is a MAL supplement, so it is intentionally registered here instead of
    the metadata-source registry used for AnimeIdentity/direct lookup.
    """

    return (JikanSource(),)
