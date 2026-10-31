from __future__ import annotations

import re
from collections import Counter
from datetime import datetime, timezone

from core.canonicalization import (
    canonical_role_token,
    is_localization_role,
    normalize_key,
    person_identity_keys,
    preferred_person_name,
    studio_identity_key,
)
from core.contracts import AnimeSource
from core.models import AggregatedAnime, AnimeRecord, BroadcastSlot, PersonCredit
from core.temporal import PartialDate, format_time, parse_time
from localization import canonicalize_domain_value


PAREN_NAME_RE = re.compile(r"^(.*?)\s*\((.*)\)\s*$")
SEASON_SUFFIX_RE = re.compile(r"^(.*?)\s+(\d{4})$")
SEASON_PREFIX_RE = re.compile(r"^(\d{4})[_\s-]+(.+)$")


def _clean(value: str) -> str:
    return " ".join((value or "").split()).strip()


def _dedupe_strings(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        value = _clean(value)
        key = value.casefold()
        if value and key not in seen:
            seen.add(key)
            result.append(value)
    return result


def _normalized_portraits(values: dict[str, list[str]]) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for source, urls in values.items():
        source = _clean(source)
        cleaned = _dedupe_strings(list(urls or []))
        if source and cleaned:
            result[source] = cleaned
    return result


def _merge_portraits(
    target: dict[str, list[str]],
    values: dict[str, list[str]],
) -> None:
    for source, urls in _normalized_portraits(values).items():
        target[source] = _dedupe_strings([*target.get(source, []), *urls])


def _person_names(person: PersonCredit) -> list[str]:
    result: list[str] = []
    for raw_value in [person.name, *person.aliases]:
        value = _clean(raw_value)
        if not value:
            continue
        match = PAREN_NAME_RE.match(value)
        if not match:
            result.append(value)
            continue
        base = _clean(match.group(1))
        if base:
            result.append(base)
        result.extend(_clean(part) for part in match.group(2).split(","))
    return _dedupe_strings(result)


def _external_ids_match(
    left: dict[str, str],
    right: dict[str, str],
) -> bool:
    for source in set(left) & set(right):
        left_value = _clean(str(left.get(source) or ""))
        right_value = _clean(str(right.get(source) or ""))
        if left_value and right_value and left_value == right_value:
            return True
    return False


def _external_ids_conflict(
    left: dict[str, str],
    right: dict[str, str],
) -> bool:
    for source in set(left) & set(right):
        left_value = _clean(str(left.get(source) or ""))
        right_value = _clean(str(right.get(source) or ""))
        if left_value and right_value and left_value != right_value:
            return True
    return False


def _merge_people(
    groups: list[list[PersonCredit]],
    *,
    drop_localization_roles: bool = False,
) -> list[PersonCredit]:
    merged: list[PersonCredit] = []
    identity_sets: list[set[str]] = []

    for group in groups:
        for person in group:
            if drop_localization_roles and any(
                is_localization_role(role) for role in person.roles if role
            ):
                continue

            names = _person_names(person)
            raw_roles = [role for role in person.roles if role]
            roles = _dedupe_strings(
                [
                    canonical_role_token(role)
                    for role in raw_roles
                    if canonical_role_token(role)
                ]
            )
            keys = person_identity_keys(names)
            match_index: int | None = None

            for index, existing in enumerate(merged):
                if _external_ids_match(existing.external_ids, person.external_ids):
                    match_index = index
                    break
                if _external_ids_conflict(existing.external_ids, person.external_ids):
                    continue
                if keys and keys & identity_sets[index]:
                    match_index = index
                    break

            if match_index is None:
                preferred = preferred_person_name(names, locale="en")
                aliases = [
                    value
                    for value in names
                    if normalize_key(value) != normalize_key(preferred)
                ]
                merged.append(
                    PersonCredit(
                        name=preferred,
                        roles=roles,
                        aliases=_dedupe_strings(aliases),
                        external_ids=dict(person.external_ids),
                        portraits=_normalized_portraits(person.portraits),
                    )
                )
                identity_sets.append(keys)
                continue

            current = merged[match_index]
            all_names = _dedupe_strings([current.name, *current.aliases, *names])
            preferred = preferred_person_name(all_names, locale="en")
            current.name = preferred
            current.aliases = _dedupe_strings(
                [
                    value
                    for value in all_names
                    if normalize_key(value) != normalize_key(preferred)
                ]
            )
            current.roles = _dedupe_strings([*current.roles, *roles])
            current.external_ids.update(
                {key: value for key, value in person.external_ids.items() if value}
            )
            _merge_portraits(current.portraits, person.portraits)
            identity_sets[match_index] |= keys

    return merged


def _merge_studios(records: list[AnimeRecord]) -> list[str]:
    merged: dict[str, str] = {}
    order: list[str] = []
    for record in records:
        for raw_value in record.studios:
            value = _clean(raw_value)
            key = studio_identity_key(value)
            if not value or not key:
                continue
            if key not in merged:
                merged[key] = value
                order.append(key)
    return [merged[key] for key in order]


def _consensus_values(values: list[str]) -> str | None:
    values = [_clean(value) for value in values if _clean(value)]
    if not values:
        return None
    keys = [normalize_key(value) or value.casefold() for value in values]
    counts = Counter(keys)
    best_count = max(counts.values())
    for value, key in zip(values, keys):
        if counts[key] == best_count:
            return value
    return values[0]


def _consensus_text(records: list[AnimeRecord], field_name: str) -> str | None:
    return _consensus_values(
        [
            value
            for record in records
            if isinstance((value := getattr(record, field_name)), str)
        ]
    )


def _consensus_partial_date(
    records: list[AnimeRecord],
    field_name: str,
) -> PartialDate | None:
    values = [
        value
        for record in records
        if isinstance((value := getattr(record, field_name)), PartialDate)
    ]
    if not values:
        return None
    counts = Counter(value.isoformat() for value in values)
    best = max(counts.values())
    return next(value for value in values if counts[value.isoformat()] == best)


def _consensus_datetime(
    records: list[AnimeRecord],
    field_name: str,
) -> datetime | None:
    values = [
        value
        for record in records
        if isinstance((value := getattr(record, field_name)), datetime)
    ]
    if not values:
        return None

    def instant_key(value: datetime) -> str:
        if value.tzinfo is None:
            return value.isoformat()
        return value.astimezone(timezone.utc).isoformat()

    counts = Counter(instant_key(value) for value in values)
    best = max(counts.values())
    return next(value for value in values if counts[instant_key(value)] == best)


def _consensus_domain(
    records: list[AnimeRecord],
    field_name: str,
    domain: str,
) -> str | None:
    values: list[str] = []
    for record in records:
        value = getattr(record, field_name)
        if not isinstance(value, str) or not _clean(value):
            continue
        canonical = canonicalize_domain_value(domain, value)
        if canonical:
            values.append(canonical)
    return _consensus_values(values)


def _consensus_rating(records: list[AnimeRecord]) -> str | None:
    """Choose a conservative canonical age rating across metadata sources.

    ``none`` never wins over an explicit rating. For equally supported explicit
    values, prefer the more restrictive category so a sparse/coarse provider
    cannot make the public card look less restrictive than another source.
    """

    values: list[str] = []
    for record in records:
        value = record.rating
        if not isinstance(value, str) or not _clean(value):
            continue
        canonical = canonicalize_domain_value("rating", value)
        if canonical:
            values.append(canonical)
    if not values:
        return None

    explicit = [value for value in values if value != "none"]
    if explicit:
        values = explicit
    counts = Counter(values)
    best_count = max(counts.values())
    candidates = [value for value, count in counts.items() if count == best_count]
    severity = {
        "none": 0,
        "g": 1,
        "pg": 2,
        "pg_13": 3,
        "r": 4,
        "r_plus": 5,
        "adult": 6,
        "rx": 7,
    }
    return max(candidates, key=lambda value: severity.get(value, 0))


def _consensus_int(
    records: list[AnimeRecord],
    field_name: str,
    *,
    prefer_max_on_tie: bool = False,
) -> int | None:
    values: list[int] = []
    for record in records:
        value = getattr(record, field_name)
        if isinstance(value, int) and not isinstance(value, bool):
            values.append(value)
    if not values:
        return None

    counts = Counter(values)
    best_count = max(counts.values())
    candidates = [value for value, count in counts.items() if count == best_count]
    if prefer_max_on_tie:
        return max(candidates)
    for value in values:
        if value in candidates:
            return value
    return values[0]


def _max_int(records: list[AnimeRecord], field_name: str) -> int | None:
    values = [
        getattr(record, field_name)
        for record in records
        if isinstance(getattr(record, field_name), int)
        and not isinstance(getattr(record, field_name), bool)
    ]
    return max(values) if values else None


def _min_positive_int(records: list[AnimeRecord], field_name: str) -> int | None:
    values = [
        getattr(record, field_name)
        for record in records
        if isinstance(getattr(record, field_name), int)
        and not isinstance(getattr(record, field_name), bool)
        and getattr(record, field_name) > 0
    ]
    return min(values) if values else None


def _season_parts(record: AnimeRecord) -> tuple[str | None, int | None]:
    raw = _clean(record.season or "")
    year = record.season_year
    if not raw:
        return None, year

    suffix = SEASON_SUFFIX_RE.match(raw)
    if suffix and year is None:
        raw = _clean(suffix.group(1))
        year = int(suffix.group(2))

    prefix = SEASON_PREFIX_RE.match(raw)
    if prefix and year is None:
        year = int(prefix.group(1))
        raw = _clean(prefix.group(2))

    return canonicalize_domain_value("season", raw), year


def _merge_season(records: list[AnimeRecord]) -> tuple[str | None, int | None]:
    seasons: list[str] = []
    years: list[int] = []
    for record in records:
        season, year = _season_parts(record)
        if season:
            seasons.append(season)
        if year:
            years.append(year)
    season = _consensus_values(seasons)
    year = None
    if years:
        counts = Counter(years)
        best = max(counts.values())
        year = next(value for value in years if counts[value] == best)
    return season, year


def _merge_broadcasts(records: list[AnimeRecord]) -> list[BroadcastSlot]:
    result: list[BroadcastSlot] = []
    seen: set[tuple[str, str]] = set()
    for record in records:
        for item in record.broadcasts:
            if isinstance(item, BroadcastSlot):
                weekday = (
                    canonicalize_domain_value("weekday", item.weekday)
                    if item.weekday
                    else None
                )
                broadcast_time = item.time
            else:
                weekday = None
                broadcast_time = parse_time(item)
            key = (weekday or "", format_time(broadcast_time) or "")
            if key == ("", "") or key in seen:
                continue
            seen.add(key)
            result.append(BroadcastSlot(weekday=weekday, time=broadcast_time))
    return result


def _best_text(values: list[str]) -> str | None:
    unique = _dedupe_strings(values)
    if not unique:
        return None
    return max(unique, key=lambda value: (len(value), value.casefold()))


def _merge_source_text(target: dict[str, str], values: dict[str, str]) -> None:
    for source, value in values.items():
        source = _clean(source)
        value = _clean(value)
        if not source or not value:
            continue
        existing = target.get(source)
        if existing is None or len(value) > len(existing):
            target[source] = value


class AggregationMergeSupport:
    """Shared merge operations independent from anime identity resolution."""

    def __init__(self, sources: tuple[AnimeSource, ...] | list[AnimeSource]) -> None:
        self._sources = tuple(sources)

    def merge_people_source(
        self,
        anime: AggregatedAnime,
        *,
        source_name: str,
        people: list[PersonCredit],
        section: str,
    ) -> None:
        if section == "staff":
            mapping = anime.staff_by_source
            drop_localization_roles = True
        elif section == "voices":
            mapping = anime.voices_by_source
            drop_localization_roles = False
        else:
            raise ValueError(f"Unsupported people section: {section}")

        normalized = _merge_people(
            [people],
            drop_localization_roles=drop_localization_roles,
        )
        if normalized:
            mapping[source_name] = normalized
        else:
            mapping.pop(source_name, None)

        ordered_groups = [
            mapping[source] for source in anime.sources if source in mapping
        ]
        ordered_groups.extend(
            people_group
            for source, people_group in mapping.items()
            if source not in anime.sources
        )
        merged = _merge_people(
            ordered_groups,
            drop_localization_roles=drop_localization_roles,
        )

        if section == "staff":
            anime.staff = merged
        else:
            anime.voices = merged
