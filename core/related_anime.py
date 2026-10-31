from __future__ import annotations

from dataclasses import dataclass, field

from core.identity import AnimeIdentity
from core.models import SearchCandidate


_RELATION_ALIASES = {
    "prequel": "prequel",
    "sequel": "sequel",
    "parent": "parent",
    "parent_story": "parent",
    "parent story": "parent",
    "side_story": "side_story",
    "side story": "side_story",
    "spin_off": "spin_off",
    "spin-off": "spin_off",
    "spin off": "spin_off",
    "alternative": "alternative",
    "alternative_setting": "alternative_setting",
    "alternative setting": "alternative_setting",
    "alternative_version": "alternative_version",
    "alternative version": "alternative_version",
    "summary": "summary",
    "full_story": "full_story",
    "full story": "full_story",
    "adaptation": "adaptation",
    "source": "source",
    "character": "character",
    "compilation": "compilation",
    "contains": "contains",
    "other": "other",
}

RELATION_ORDER = {
    "prequel": 0,
    "sequel": 1,
    "parent": 2,
    "side_story": 3,
    "spin_off": 4,
    "alternative": 5,
    "alternative_setting": 6,
    "alternative_version": 7,
    "summary": 8,
    "full_story": 9,
    "compilation": 10,
    "contains": 11,
    "adaptation": 12,
    "source": 13,
    "character": 14,
    "other": 15,
}


def canonical_relation_kind(value: object) -> str:
    raw = " ".join(str(value or "").strip().casefold().split())
    normalized = raw.replace("__", "_")
    return _RELATION_ALIASES.get(
        normalized,
        _RELATION_ALIASES.get(raw, normalized.replace(" ", "_") or "other"),
    )


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for raw in values:
        value = " ".join(str(raw or "").split()).strip()
        key = value.casefold()
        if value and key not in seen:
            seen.add(key)
            result.append(value)
    return result


def _candidate_title(titles: dict[str, str], aliases: list[str]) -> str:
    for key in ("romaji", "english", "russian", "japanese"):
        value = str(titles.get(key) or "").strip()
        if value:
            return value
    return next((value for value in aliases if str(value).strip()), "Unknown anime")


@dataclass(slots=True)
class AnimeReference:
    """One source-scoped related/recommended anime reference."""

    source: str
    titles: dict[str, str] = field(default_factory=dict)
    aliases: list[str] = field(default_factory=list)
    external_ids: dict[str, str] = field(default_factory=dict)
    posters: list[str] = field(default_factory=list)
    relation: str | None = None
    rank: int = 1

    @property
    def identity(self) -> AnimeIdentity:
        return AnimeIdentity.from_mapping(self.external_ids)


@dataclass(slots=True)
class AggregatedAnimeReference:
    """Cross-source reference merged only by confirmed peer IDs."""

    titles: dict[str, str] = field(default_factory=dict)
    aliases: list[str] = field(default_factory=list)
    external_ids: dict[str, str] = field(default_factory=dict)
    posters: list[str] = field(default_factory=list)
    relations: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    rank_score: float = 0.0

    @property
    def identity(self) -> AnimeIdentity:
        return AnimeIdentity.from_mapping(self.external_ids)

    @property
    def candidate(self) -> SearchCandidate:
        title = _candidate_title(self.titles, self.aliases)
        title_values = [value for value in self.titles.values() if str(value).strip()]
        aliases = _dedupe([*title_values, *self.aliases])
        aliases = [value for value in aliases if value.casefold() != title.casefold()]
        return SearchCandidate(
            title=title,
            aliases=aliases,
            external_ids=dict(self.external_ids),
            romaji_title=self.titles.get("romaji"),
            posters=_dedupe(self.posters),
        )
