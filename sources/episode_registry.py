from __future__ import annotations

from core.contracts import AnimeEpisodeSource
from core.settings import SourceSettings, get_settings
from sources.anidb import AniDBSource
from sources.jikan import JikanSource


def get_episode_sources(
    settings: SourceSettings | None = None,
) -> tuple[AnimeEpisodeSource, ...]:
    """Return registered lazy episode backends."""
    settings = settings or get_settings().sources
    sources: list[AnimeEpisodeSource] = [JikanSource(settings)]
    if AniDBSource.is_enabled(settings):
        sources.append(AniDBSource(settings))
    return tuple(sources)
