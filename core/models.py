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
    """One person participating in an anime.

    ``name`` is the preferred display value. ``aliases`` keeps alternate
    spellings/languages so the aggregator can identify the same person across
    Russian and international databases. ``external_ids`` keeps source-local
    person IDs. ``portraits`` keeps source-keyed image URLs so the merged UI can
    show every available portrait or one database at a time without losing
    provenance.
    """

    name: str
    roles: list[str] = field(default_factory=list)
    aliases: list[str] = field(default_factory=list)
    external_ids: dict[str, str] = field(default_factory=dict)
    portraits: dict[str, list[str]] = field(default_factory=dict)


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

    # The merged values above remain the default UI representation. These
    # source-preserving buckets make it possible to switch the same section to
    # one database without re-fetching or losing the semantically merged view.
    titles_by_source: dict[str, dict[str, str]] = field(default_factory=dict)
    synonyms_by_source: dict[str, list[str]] = field(default_factory=dict)
    staff_by_source: dict[str, list[PersonCredit]] = field(default_factory=dict)
    voices_by_source: dict[str, list[PersonCredit]] = field(default_factory=dict)

    # Some fields are intentionally kept by source because the distinction is
    # useful in the UI (for example descriptions and links).
    descriptions: dict[str, str] = field(default_factory=dict)
    background: str | None = None
    posters: list[str] = field(default_factory=list)
    urls: dict[str, str] = field(default_factory=dict)
    staff: list[PersonCredit] = field(default_factory=list)
    voices: list[PersonCredit] = field(default_factory=list)
    errors: dict[str, str] = field(default_factory=dict)
