from __future__ import annotations

from core.contracts import AnimeEpisodeSource
from sources.anidb import AniDBSource
from sources.jikan import JikanSource


def get_episode_sources() -> tuple[AnimeEpisodeSource, ...]:
    """Return registered lazy episode backends."""
    sources: list[AnimeEpisodeSource] = [JikanSource()]
    if AniDBSource.is_enabled():
        sources.append(AniDBSource())
    return tuple(sources)
