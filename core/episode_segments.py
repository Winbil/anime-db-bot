from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class EpisodeSegment:
    """Normalized time range inside one anime episode.

    Timestamp providers are capability backends, not anime identity databases, so
    ``source`` stores the backend key (for example ``aniskip``) rather than a
    :class:`core.source_keys.SourceKey` value.
    """

    kind: str
    source: str
    start_seconds: float | None = None
    end_seconds: float | None = None
    source_segment_id: str | None = None
    raw_kind: str | None = None
    episode_length_seconds: float | None = None


@dataclass(frozen=True, slots=True)
class AggregatedEpisodeSegment:
    """Consensus view of compatible evidence from timestamp providers."""

    kind: str
    start_seconds: float | None
    end_seconds: float | None
    sources: tuple[str, ...]
    evidence: tuple[EpisodeSegment, ...]
