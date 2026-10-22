from __future__ import annotations

from dataclasses import dataclass, field

from core.identity import AnimeIdentity


@dataclass(slots=True)
class SearchCandidate:
    """One anime candidate discovered by one or more search providers."""

    title: str
    aliases: list[str] = field(default_factory=list)
    year: int | None = None
    external_ids: dict[str, str] = field(default_factory=dict)
    scores: dict[str, float] = field(default_factory=dict)

    @property
    def identity(self) -> AnimeIdentity:
        return AnimeIdentity.from_mapping(self.external_ids)


@dataclass(slots=True)
class SearchPage:
    items: list[SearchCandidate]
    page: int
    page_size: int
    has_next: bool
    errors: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class BroadcastSlot:
    """Locale-neutral broadcast schedule entry."""

    weekday: str | None = None
    time: str | None = None


@dataclass(slots=True)
class PersonCredit:
    """One person participating in an anime.

    ``name`` and ``aliases`` contain raw name variants. They are not a finished
    presentation string; platform renderers choose the preferred variant for the
    current interface locale. ``roles`` stores canonical role keys when known,
    while unknown upstream roles remain as raw strings. Dynamic voice credits use
    the internal ``voice_of::<character>`` token. ``external_ids`` keeps
    source-local person IDs and ``portraits`` keeps source-keyed image URLs.
    """

    name: str
    roles: list[str] = field(default_factory=list)
    aliases: list[str] = field(default_factory=list)
    external_ids: dict[str, str] = field(default_factory=dict)
    portraits: dict[str, list[str]] = field(default_factory=dict)


@dataclass(slots=True)
class AnimeRecord:
    """Normalized locale-neutral metadata returned by one source.

    Source adapters map external enum values to canonical keys. Translation is a
    platform/UI responsibility and must not happen inside adapters or aggregation.
    Unknown upstream values are preserved as raw strings for forward compatibility.
    ``external_ids`` is a peer set of source IDs: no database is the primary key.
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
    season_year: int | None = None
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
    broadcasts: list[BroadcastSlot] = field(default_factory=list)

    descriptions: dict[str, str] = field(default_factory=dict)
    backgrounds: list[str] = field(default_factory=list)
    posters: list[str] = field(default_factory=list)
    urls: dict[str, str] = field(default_factory=dict)
    staff: list[PersonCredit] = field(default_factory=list)
    voices: list[PersonCredit] = field(default_factory=list)

    @property
    def identity(self) -> AnimeIdentity:
        values = dict(self.external_ids)
        source_key = self.source.strip().casefold()
        if source_key and self.source_id:
            aliases = {
                "myanimelist": "mal",
                "anilist": "anilist",
                "shikimori": "shikimori",
            }
            values.setdefault(aliases.get(source_key, source_key), str(self.source_id))
        return AnimeIdentity.from_mapping(values)


@dataclass(slots=True)
class AggregatedAnime:
    """One source-independent locale-neutral anime card."""

    title: str
    titles: dict[str, str] = field(default_factory=dict)
    synonyms: list[str] = field(default_factory=list)
    external_ids: dict[str, str] = field(default_factory=dict)
    sources: list[str] = field(default_factory=list)

    kind: str | None = None
    status: str | None = None
    rating: str | None = None
    season: str | None = None
    season_year: int | None = None
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
    broadcasts: list[BroadcastSlot] = field(default_factory=list)

    titles_by_source: dict[str, dict[str, str]] = field(default_factory=dict)
    synonyms_by_source: dict[str, list[str]] = field(default_factory=dict)
    staff_by_source: dict[str, list[PersonCredit]] = field(default_factory=dict)
    voices_by_source: dict[str, list[PersonCredit]] = field(default_factory=dict)

    descriptions: dict[str, str] = field(default_factory=dict)
    background: str | None = None
    posters: list[str] = field(default_factory=list)
    urls: dict[str, str] = field(default_factory=dict)
    staff: list[PersonCredit] = field(default_factory=list)
    voices: list[PersonCredit] = field(default_factory=list)
    errors: dict[str, str] = field(default_factory=dict)

    @property
    def identity(self) -> AnimeIdentity:
        return AnimeIdentity.from_mapping(self.external_ids)
