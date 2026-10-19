from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class SearchCandidate:
    """One result returned by the dedicated search provider."""

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
    """Normalized metadata returned by one source for a selected MAL ID."""

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
    genres: list[str] = field(default_factory=list)
    studios: list[str] = field(default_factory=list)
    licensors: list[str] = field(default_factory=list)
    descriptions: dict[str, str] = field(default_factory=dict)
    posters: list[str] = field(default_factory=list)
    urls: dict[str, str] = field(default_factory=dict)
    staff: list[PersonCredit] = field(default_factory=list)
    voices: list[PersonCredit] = field(default_factory=list)


@dataclass(slots=True)
class AggregatedAnime:
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
    genres: list[str] = field(default_factory=list)
    studios: list[str] = field(default_factory=list)
    licensors: list[str] = field(default_factory=list)
    descriptions: dict[str, str] = field(default_factory=dict)
    posters: list[str] = field(default_factory=list)
    urls: dict[str, str] = field(default_factory=dict)
    staff: list[PersonCredit] = field(default_factory=list)
    voices: list[PersonCredit] = field(default_factory=list)
    errors: dict[str, str] = field(default_factory=dict)
