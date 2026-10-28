from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from core.character_identity import CharacterIdentity
from core.identity import AnimeIdentity
from core.temporal import PartialDate, parse_datetime, parse_partial_date


@dataclass(slots=True)
class SearchCandidate:
    """One anime candidate discovered by one or more search providers.

    ``romaji_title`` is an explicit cross-provider title-matching hint. It is
    kept separate from ``title``/``aliases`` so search merge does not have to
    guess which display title is the romanized Japanese title. ``posters`` keeps
    lightweight preview artwork returned by search/direct-ID lookups so Telegram
    can render a result preview without loading the full anime card first.
    """

    title: str
    aliases: list[str] = field(default_factory=list)
    year: int | None = None
    external_ids: dict[str, str] = field(default_factory=dict)
    scores: dict[str, float] = field(default_factory=dict)
    romaji_title: str | None = None
    posters: list[str] = field(default_factory=list)

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


@dataclass(slots=True)
class SearchResultSet:
    """Query-scoped merged results used by interactive search pagination.

    ``complete`` is false when collection stopped because of a configured
    upstream page/candidate safety cap while relevant provider results were still
    available. UI code must then present the accumulated count as non-final.
    """

    items: list[SearchCandidate]
    complete: bool = True
    errors: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class BroadcastSlot:
    """Locale-neutral broadcast schedule entry."""

    weekday: str | None = None
    time: str | None = None


@dataclass(frozen=True, slots=True)
class TrailerRecord:
    """One source-scoped promotional trailer.

    ``source`` is the logical database identity key (``mal``, ``anilist`` or
    ``shikimori``) while ``backend`` records the concrete backend used to fetch
    the trailer. This keeps MAL/Jikan provenance explicit without inventing a
    Jikan identity key.
    """

    source: str
    backend: str
    url: str
    title: str | None = None
    kind: str = "trailer"
    hosting: str | None = None
    embed_url: str | None = None
    thumbnail: str | None = None


@dataclass(slots=True)
class EpisodeRecord:
    """One source-scoped anime episode record.

    ``source`` identifies the logical database (currently ``mal`` for Jikan-backed
    data) while ``backend`` records how the value was obtained. Jikan therefore
    supplements MAL without becoming a new AnimeIdentity key.
    """

    number: int
    source: str
    backend: str
    titles: dict[str, str] = field(default_factory=dict)
    aired_at: PartialDate | None = None
    duration_seconds: int | None = None
    score: float | None = None
    filler: bool = False
    recap: bool = False
    synopsis: str | None = None
    urls: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.aired_at = parse_partial_date(self.aired_at)


@dataclass(slots=True)
class EpisodePage:
    items: list[EpisodeRecord]
    page: int
    last_visible_page: int = 1
    has_next: bool = False


@dataclass(frozen=True, slots=True)
class PopularityRanking:
    """One source-local leaderboard position.

    ``kind`` is a locale-neutral key such as ``rated`` or ``popular``.
    ``season`` uses the same canonical season keys as the anime model.
    """

    rank: int
    kind: str
    year: int | None = None
    season: str | None = None
    all_time: bool = False


@dataclass(slots=True)
class PopularityStats:
    """Audience/popularity statistics belonging to exactly one source."""

    rank: int | None = None
    popularity_rank: int | None = None
    list_users: int | None = None
    scoring_users: int | None = None
    favorites: int | None = None
    status_distribution: dict[str, int] = field(default_factory=dict)
    score_distribution: dict[int, int] = field(default_factory=dict)
    rankings: list[PopularityRanking] = field(default_factory=list)

    def has_data(self) -> bool:
        return any(
            (
                self.rank is not None,
                self.popularity_rank is not None,
                self.list_users is not None,
                self.scoring_users is not None,
                self.favorites is not None,
                bool(self.status_distribution),
                bool(self.score_distribution),
                bool(self.rankings),
            )
        )


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
class CharacterRecord:
    """One source-scoped anime character used by lazy character views.

    Names stay locale-neutral/raw, ``role`` is a canonical key when known,
    external IDs remain source-scoped, and portraits keep their provenance.
    """

    name: str
    role: str | None = None
    aliases: list[str] = field(default_factory=list)
    external_ids: dict[str, str] = field(default_factory=dict)
    portraits: dict[str, list[str]] = field(default_factory=dict)

    @property
    def identity(self) -> CharacterIdentity:
        return CharacterIdentity.from_mapping(self.external_ids)


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
    aired_on: PartialDate | None = None
    released_on: PartialDate | None = None
    next_episode_at: datetime | None = None

    score: float | None = None
    rank: int | None = None
    popularity_rank: int | None = None
    list_users: int | None = None
    scoring_users: int | None = None
    favorites: int | None = None
    status_distribution: dict[str, int] = field(default_factory=dict)
    score_distribution: dict[int, int] = field(default_factory=dict)
    rankings: list[PopularityRanking] = field(default_factory=list)

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

    def __post_init__(self) -> None:
        self.aired_on = parse_partial_date(self.aired_on)
        self.released_on = parse_partial_date(self.released_on)
        self.next_episode_at = parse_datetime(self.next_episode_at)

    @property
    def identity(self) -> AnimeIdentity:
        values = dict(self.external_ids)
        source_key = self.source.strip().casefold()
        if source_key and self.source_id:
            aliases = {
                "myanimelist": "mal",
                "mal (myanimelist) / jikan": "mal",
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
    aired_on: PartialDate | None = None
    released_on: PartialDate | None = None
    next_episode_at: datetime | None = None

    scores: dict[str, float] = field(default_factory=dict)
    score_average: float | None = None
    score_sources_count: int = 0
    rank: int | None = None
    popularity_rank: int | None = None
    list_users: int | None = None
    scoring_users: int | None = None
    favorites: int | None = None
    popularity_by_source: dict[str, PopularityStats] = field(default_factory=dict)

    genres: list[str] = field(default_factory=list)
    studios: list[str] = field(default_factory=list)
    licensors: list[str] = field(default_factory=list)
    source_materials: list[str] = field(default_factory=list)
    broadcasts: list[BroadcastSlot] = field(default_factory=list)

    titles_by_source: dict[str, dict[str, str]] = field(default_factory=dict)
    synonyms_by_source: dict[str, list[str]] = field(default_factory=dict)
    staff_by_source: dict[str, list[PersonCredit]] = field(default_factory=dict)
    voices_by_source: dict[str, list[PersonCredit]] = field(default_factory=dict)
    characters_by_source: dict[str, list[CharacterRecord]] = field(default_factory=dict)

    descriptions: dict[str, str] = field(default_factory=dict)
    background: str | None = None
    posters: list[str] = field(default_factory=list)
    urls: dict[str, str] = field(default_factory=dict)
    staff: list[PersonCredit] = field(default_factory=list)
    voices: list[PersonCredit] = field(default_factory=list)
    characters: list[CharacterRecord] = field(default_factory=list)
    errors: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.aired_on = parse_partial_date(self.aired_on)
        self.released_on = parse_partial_date(self.released_on)
        self.next_episode_at = parse_datetime(self.next_episode_at)

    @property
    def identity(self) -> AnimeIdentity:
        return AnimeIdentity.from_mapping(self.external_ids)
