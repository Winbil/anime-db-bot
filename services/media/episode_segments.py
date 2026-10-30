from __future__ import annotations

import asyncio
import logging
from statistics import median
from typing import Protocol

from core.episode_segments import AggregatedEpisodeSegment, EpisodeSegment
from core.identity import AnimeIdentity

SEGMENT_MERGE_TOLERANCE_SECONDS = 5.0
_KIND_ORDER = {
    "recap": 0,
    "branding": 1,
    "opening": 2,
    "mixed_opening": 3,
    "title_card": 4,
    "transition": 5,
    "filler": 6,
    "ending": 7,
    "mixed_ending": 8,
    "preview": 9,
    "credits": 10,
    "post_credits": 11,
    "other": 99,
}


class EpisodeSegmentSource(Protocol):
    name: str
    display_name: str
    backend_key: str

    def supports_identity(self, identity: AnimeIdentity) -> bool: ...

    async def load_segments(
        self,
        identity: AnimeIdentity,
        episode_number: int,
        *,
        episode_length_seconds: int | None = None,
    ) -> list[EpisodeSegment]: ...


def _compatible(left: EpisodeSegment, right: EpisodeSegment) -> bool:
    checks: list[bool] = []
    if left.start_seconds is not None and right.start_seconds is not None:
        checks.append(
            abs(left.start_seconds - right.start_seconds)
            <= SEGMENT_MERGE_TOLERANCE_SECONDS
        )
    if left.end_seconds is not None and right.end_seconds is not None:
        checks.append(
            abs(left.end_seconds - right.end_seconds) <= SEGMENT_MERGE_TOLERANCE_SECONDS
        )
    return bool(checks) and all(checks)


def _median(values: list[float]) -> float | None:
    return float(median(values)) if values else None


def aggregate_segments(
    by_source: dict[str, list[EpisodeSegment]],
) -> list[AggregatedEpisodeSegment]:
    """Build a conservative consensus without averaging unrelated intervals.

    Evidence is clustered only when every comparable boundary is within five
    seconds. The largest compatible cluster wins for each normalized segment
    kind, and its boundary values use medians so a single outlier cannot drag the
    result away from the consensus.
    """

    grouped: dict[str, list[EpisodeSegment]] = {}
    for segments in by_source.values():
        for segment in segments:
            grouped.setdefault(segment.kind, []).append(segment)

    result: list[AggregatedEpisodeSegment] = []
    for kind, evidence in grouped.items():
        clusters: list[list[EpisodeSegment]] = []
        for segment in evidence:
            target = next(
                (
                    cluster
                    for cluster in clusters
                    if all(_compatible(segment, other) for other in cluster)
                ),
                None,
            )
            if target is None:
                clusters.append([segment])
            else:
                target.append(segment)
        winner = max(clusters, key=len)
        starts = [value for item in winner if (value := item.start_seconds) is not None]
        ends = [value for item in winner if (value := item.end_seconds) is not None]
        sources = tuple(dict.fromkeys(item.source for item in winner))
        result.append(
            AggregatedEpisodeSegment(
                kind=kind,
                start_seconds=_median(starts),
                end_seconds=_median(ends),
                sources=sources,
                evidence=tuple(winner),
            )
        )
    result.sort(
        key=lambda item: (
            _KIND_ORDER.get(item.kind, 50),
            item.start_seconds if item.start_seconds is not None else float("inf"),
        )
    )
    return result


class EpisodeSegmentService:
    """Timestamp capability kept independent from episode metadata backends."""

    def __init__(
        self,
        sources: tuple[EpisodeSegmentSource, ...] | list[EpisodeSegmentSource],
    ) -> None:
        self._sources = tuple(sources)
        self._by_backend = {source.backend_key: source for source in self._sources}

    @property
    def sources(self) -> tuple[EpisodeSegmentSource, ...]:
        return self._sources

    def available_backends(self, identity: AnimeIdentity) -> list[str]:
        return [
            source.backend_key
            for source in self._sources
            if source.supports_identity(identity)
        ]

    def display_name(self, backend: str) -> str:
        source = self._by_backend.get(backend)
        return source.display_name if source is not None else backend

    async def load_segments(
        self,
        identity: AnimeIdentity,
        episode_number: int,
        *,
        backend: str,
        episode_length_seconds: int | None = None,
    ) -> list[EpisodeSegment]:
        source = self._by_backend.get(backend)
        if source is None:
            raise ValueError(f"Unknown episode segment backend: {backend}")
        if not source.supports_identity(identity):
            return []
        return await source.load_segments(
            identity,
            episode_number,
            episode_length_seconds=episode_length_seconds,
        )

    async def load_all(
        self,
        identity: AnimeIdentity,
        episode_number: int,
        *,
        episode_length_seconds: int | None = None,
    ) -> tuple[dict[str, list[EpisodeSegment]], dict[str, str]]:
        backends = self.available_backends(identity)

        async def load_one(
            backend: str,
        ) -> tuple[str, list[EpisodeSegment], str | None]:
            try:
                values = await self.load_segments(
                    identity,
                    episode_number,
                    backend=backend,
                    episode_length_seconds=episode_length_seconds,
                )
                return backend, values, None
            except Exception as exc:
                logging.exception(
                    "Could not load %s episode timestamps",
                    self.display_name(backend),
                )
                return backend, [], exc.__class__.__name__

        loaded = await asyncio.gather(*(load_one(backend) for backend in backends))
        by_source: dict[str, list[EpisodeSegment]] = {}
        errors: dict[str, str] = {}
        for backend, values, error in loaded:
            by_source[backend] = values
            if error:
                errors[backend] = error
        return by_source, errors

    async def load_aggregated(
        self,
        identity: AnimeIdentity,
        episode_number: int,
        *,
        episode_length_seconds: int | None = None,
    ) -> tuple[list[AggregatedEpisodeSegment], dict[str, str]]:
        by_source, errors = await self.load_all(
            identity,
            episode_number,
            episode_length_seconds=episode_length_seconds,
        )
        return aggregate_segments(by_source), errors
