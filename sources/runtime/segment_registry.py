from __future__ import annotations

from services.media.episode_segments import EpisodeSegmentSource
from sources.providers.aniskip import AniSkipSegmentSource


def get_episode_segment_sources() -> tuple[EpisodeSegmentSource, ...]:
    """Return timestamp backends independently from episode metadata sources."""

    return (AniSkipSegmentSource(),)
