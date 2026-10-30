from __future__ import annotations

from core.settings import SourceSettings
from services.media.episode_segments import EpisodeSegmentSource
from sources.providers.anime_skip import AnimeSkipSegmentSource
from sources.providers.aniskip import AniSkipSegmentSource


def get_episode_segment_sources(
    settings: SourceSettings | None = None,
) -> tuple[EpisodeSegmentSource, ...]:
    """Return timestamp backends independently from episode metadata sources."""

    sources: list[EpisodeSegmentSource] = [AniSkipSegmentSource()]
    if AnimeSkipSegmentSource.is_enabled(settings):
        sources.append(AnimeSkipSegmentSource(settings))
    return tuple(sources)
