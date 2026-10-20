from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class SearchCandidate:
    """One anime candidate discovered by one or more search providers."""

    title: str
    aliases: list[str] = field(default_factory=list)
    year: int | None = None
    external_ids: dict[str, str] = field(default_factory=dict)
    scores: dict[str, float] = field(default_factory=dict)


@dataclass(slots=True)
class SearchPage:
    items: list[SearchCandidate]
    page: int
    page_size: int
    has_next: bool
    errors: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class PersonCredit:
    name: str
    roles: list[str] = field(default_factory=list)


@dataclass(slots=True)
class AnimeRecord:
    """Normalized metadata returned by one source for a selected anime.

    Source adapters should map their own field names into these semantic fields.
    The aggregator then merges equivalent fields across every source instead of
    exposing source-specific metadata buckets to the Telegram UI.
    """

    source: str
    source_id: str
    titles: dict[str, str] = field(default_factory=dict)
    synonyms: list[str] = field(default_factory=list)
    external_ids: dict[str, str] = field(default_factory=dict)

    kind: str | None = None
    status: str | None = None
    rating: str | None = None
    season: str | None = None
    franchise: str | None = None

    episodes_total: int | None = None
    episodes_aired: int | None = None
    duration_minutes: int | None = None
    aired_on: str | None = None
    released_on: str | None = None
    next_episode_at: str | None = None

    score: float | None = None
    rank: int | None = None
    popularity_rank: int | None = None
    list_users: int | None = None
    scoring_users: int | None = None
    favorites: int | None = None

    genres: list[str] = field(default_factory=list)
    studios: list[str] = field(default_factory=list)
    licensors: list[str] = field(default_factory=list)
    source_materials: list[str] = field(default_factory=list)
    broadcasts: list[str] = field(default_factory=list)

    descriptions: dict[str, str] = field(default_factory=dict)
    backgrounds: list[str] = field(default_factory=list)
    posters: list[str] = field(default_factory=list)
    urls: dict[str, str] = field(default_factory=dict)
    staff: list[PersonCredit] = field(default_factory=list)
    voices: list[PersonCredit] = field(default_factory=list)


@dataclass(slots=True)
class AggregatedAnime:
    """One source-independent anime card assembled from all available records."""

    title: str
    titles: dict[str, str] = field(default_factory=dict)
    synonyms: list[str] = field(default_factory=list)
    external_ids: dict[str, str] = field(default_factory=dict)
    sources: list[str] = field(default_factory=list)

    kind: str | None = None
    status: str | None = None
    rating: str | None = None
    season: str | None = None
    franchise: str | None = None

    episodes_total: int | None = None
    episodes_aired: int | None = None
    duration_minutes: int | None = None
    aired_on: str | None = None
    released_on: str | None = None
    next_episode_at: str | None = None

    # Keep individual source scores for transparency while also exposing a
    # calculated average for the compact summary card.
    scores: dict[str, float] = field(default_factory=dict)
    score_average: float | None = None
    score_sources_count: int = 0
    rank: int | None = None
    popularity_rank: int | None = None
    list_users: int | None = None
    scoring_users: int | None = None
    favorites: int | None = None

    genres: list[str] = field(default_factory=list)
    studios: list[str] = field(default_factory=list)
    licensors: list[str] = field(default_factory=list)
    source_materials: list[str] = field(default_factory=list)
    broadcasts: list[str] = field(default_factory=list)

    # Descriptions and URLs intentionally remain keyed by source because the UI
    # lets the user choose which source to read/open. Equivalent list metadata
    # such as genres and studios is still merged above.
    descriptions: dict[str, str] = field(default_factory=dict)
    description: str | None = None
    background: str | None = None
    posters: list[str] = field(default_factory=list)
    urls: dict[str, str] = field(default_factory=dict)
    staff: list[PersonCredit] = field(default_factory=list)
    voices: list[PersonCredit] = field(default_factory=list)
    errors: dict[str, str] = field(default_factory=dict)
