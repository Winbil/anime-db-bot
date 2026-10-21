from __future__ import annotations

import asyncio
import re
from collections import Counter

from core.canonicalization import (
    canonical_genre,
    canonical_role,
    canonical_studio,
    is_localization_role,
    normalize_key,
    person_identity_keys,
    preferred_person_name,
    studio_identity_key,
)
from core.contracts import AnimeSource
from core.models import AggregatedAnime, AnimeRecord, PersonCredit, SearchCandidate


PAREN_NAME_RE = re.compile(r"^(.*?)\s*\((.*)\)\s*$")
CYRILLIC_NAME_RE = re.compile(r"[А-Яа-яЁё]")
LATIN_NAME_RE = re.compile(r"[A-Za-z]")
JAPANESE_NAME_RE = re.compile(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff]")


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
    names = [person.name, *person.aliases]
    parsed: list[str] = []
    for value in list(names):
        value = _clean(value)
        match = PAREN_NAME_RE.match(value)
        if not match:
            continue
        base = _clean(match.group(1))
        if base:
            parsed.append(base)
        parsed.extend(_clean(part) for part in match.group(2).split(","))
    return _dedupe_strings([*names, *parsed])


def _display_person_name(person: PersonCredit) -> str:
    """Render Russian + romaji/English + Japanese names when available.

    Identity matching still uses ``person.name`` and ``person.aliases`` before
    this final presentation step. The aliases remain untouched afterwards so
    portrait/cross-ID work can keep using the raw name variants.
    """

    primary = _clean(person.name)
    names = _dedupe_strings([primary, *person.aliases])
    if not primary:
        return "Неизвестно"

    extras: list[str] = []

    latin = next(
        (
            value
            for value in names
            if normalize_key(value) != normalize_key(primary)
            and LATIN_NAME_RE.search(value)
            and not CYRILLIC_NAME_RE.search(value)
            and not JAPANESE_NAME_RE.search(value)
        ),
        None,
    )
    japanese = next(
        (
            value
            for value in names
            if normalize_key(value) != normalize_key(primary)
            and JAPANESE_NAME_RE.search(value)
        ),
        None,
    )

    if CYRILLIC_NAME_RE.search(primary):
        if latin:
            extras.append(latin)
        if japanese:
            extras.append(japanese)
    elif LATIN_NAME_RE.search(primary):
        if japanese:
            extras.append(japanese)
    elif JAPANESE_NAME_RE.search(primary):
        if latin:
            extras.append(latin)

    return f"{primary} ({', '.join(extras)})" if extras else primary


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
            # A credit that is explicitly tied to dubbing/localization should
            # not leak into original-production staff even if the same source
            # attaches another generic role to that row.
            if drop_localization_roles and any(
                is_localization_role(role) for role in person.roles if role
            ):
                continue

            names = _person_names(person)
            raw_roles = [role for role in person.roles if role]
            roles = _dedupe_strings(
                [canonical_role(role) for role in raw_roles if canonical_role(role)]
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
                preferred = preferred_person_name(names)
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
            preferred = preferred_person_name(all_names)
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

    for person in merged:
        person.name = _display_person_name(person)

    return merged


def _merge_studios(records: list[AnimeRecord]) -> list[str]:
    merged: dict[str, str] = {}
    order: list[str] = []
    for record in records:
        for raw_value in record.studios:
            value = canonical_studio(raw_value)
            key = studio_identity_key(value)
            if not value or not key:
                continue
            if key not in merged:
                merged[key] = value
                order.append(key)
    return [merged[key] for key in order]


def _consensus_text(records: list[AnimeRecord], field_name: str) -> str | None:
    values: list[str] = []
    for record in records:
        value = getattr(record, field_name)
        if isinstance(value, str) and _clean(value):
            values.append(_clean(value))
    if not values:
        return None

    keys = [normalize_key(value) or value.casefold() for value in values]
    counts = Counter(keys)
    best_count = max(counts.values())
    for value, key in zip(values, keys):
        if counts[key] == best_count:
            return value
    return values[0]


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


def _best_text(values: list[str]) -> str | None:
    unique = _dedupe_strings(values)
    if not unique:
        return None
    return max(unique, key=lambda value: (len(value), value.casefold()))


def _average_score(scores: dict[str, float]) -> float | None:
    values = [value for value in scores.values() if isinstance(value, (int, float))]
    if not values:
        return None
    return round(sum(float(value) for value in values) / len(values), 2)


def _merge_source_text(target: dict[str, str], values: dict[str, str]) -> None:
    for source, value in values.items():
        source = _clean(source)
        value = _clean(value)
        if not source or not value:
            continue
        existing = target.get(source)
        if existing is None or len(value) > len(existing):
            target[source] = value


class AnimeAggregator:
    """Fetch and semantically merge one anime from all metadata sources."""

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
        """Replace one source's people bucket and rebuild the merged view.

        This is used by on-demand enrichments such as Shikimori seiyuu so the
        expensive source can be loaded after the main anime card is already on
        screen without re-fetching every metadata provider.
        """
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
            mapping[source]
            for source in anime.sources
            if source in mapping
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

    async def aggregate(self, candidate: SearchCandidate) -> AggregatedAnime:
        mal_id = str(candidate.external_ids.get("mal") or "").strip()
        if not mal_id:
            raise RuntimeError("Search result does not contain a MAL ID")

        known_ids = {
            key: str(value)
            for key, value in candidate.external_ids.items()
            if value is not None and str(value).strip()
        }
        known_ids["mal"] = mal_id

        async def run(source: AnimeSource):
            try:
                record = await source.get_details(mal_id, known_ids)
                return source.name, record, None
            except Exception as exc:
                return source.name, None, f"{type(exc).__name__}: {exc}"

        results = await asyncio.gather(*(run(source) for source in self._sources))
        records: list[AnimeRecord] = []
        errors: dict[str, str] = {}

        for source_name, record, error in results:
            if error:
                errors[source_name] = error
            elif record is not None:
                records.append(record)

        if not records:
            raise RuntimeError("No metadata source could provide details for this MAL ID")

        titles: dict[str, str] = {}
        synonyms: list[str] = [candidate.title, *candidate.aliases]
        external_ids = dict(known_ids)
        scores = dict(candidate.scores)
        descriptions: dict[str, str] = {}
        urls: dict[str, str] = {}
        background_values: list[str] = []
        titles_by_source: dict[str, dict[str, str]] = {}
        synonyms_by_source: dict[str, list[str]] = {}
        staff_by_source: dict[str, list[PersonCredit]] = {}
        voices_by_source: dict[str, list[PersonCredit]] = {}

        for record in records:
            source_titles = {
                key: value
                for key, raw_value in record.titles.items()
                if (value := _clean(raw_value))
            }
            source_synonyms = _dedupe_strings(record.synonyms)
            if source_titles or source_synonyms:
                titles_by_source[record.source] = source_titles
                synonyms_by_source[record.source] = source_synonyms

            source_staff = _merge_people(
                [record.staff],
                drop_localization_roles=True,
            )
            if source_staff:
                staff_by_source[record.source] = source_staff

            source_voices = _merge_people([record.voices])
            if source_voices:
                voices_by_source[record.source] = source_voices

            for key, value in source_titles.items():
                existing = titles.get(key)
                if existing is None:
                    titles[key] = value
                elif existing.casefold() != value.casefold():
                    synonyms.append(value)

            synonyms.extend(source_synonyms)
            external_ids.update({k: v for k, v in record.external_ids.items() if v})

            if record.score is not None:
                scores[record.source] = float(record.score)

            _merge_source_text(descriptions, record.descriptions)
            background_values.extend(record.backgrounds)
            urls.update(record.urls)

        chosen_titles = {value.casefold() for value in titles.values() if value}
        synonyms = [
            value
            for value in _dedupe_strings(synonyms)
            if value.casefold() not in chosen_titles
        ]

        title = (
            titles.get("russian")
            or titles.get("romaji")
            or titles.get("english")
            or candidate.title
        )

        canonical_genres = _dedupe_strings(
            [
                canonical_genre(value)
                for record in records
                for value in record.genres
                if canonical_genre(value)
            ]
        )

        return AggregatedAnime(
            title=title,
            titles=titles,
            synonyms=synonyms,
            external_ids=external_ids,
            sources=_dedupe_strings([record.source for record in records]),
            kind=_consensus_text(records, "kind"),
            status=_consensus_text(records, "status"),
            rating=_consensus_text(records, "rating"),
            season=_consensus_text(records, "season"),
            franchise=_consensus_text(records, "franchise"),
            episodes_total=_consensus_int(
                records,
                "episodes_total",
                prefer_max_on_tie=True,
            ),
            episodes_aired=_max_int(records, "episodes_aired"),
            duration_minutes=_consensus_int(records, "duration_minutes"),
            aired_on=_consensus_text(records, "aired_on"),
            released_on=_consensus_text(records, "released_on"),
            next_episode_at=_consensus_text(records, "next_episode_at"),
            scores=scores,
            score_average=_average_score(scores),
            score_sources_count=len(scores),
            rank=_min_positive_int(records, "rank"),
            popularity_rank=_min_positive_int(records, "popularity_rank"),
            list_users=_max_int(records, "list_users"),
            scoring_users=_max_int(records, "scoring_users"),
            favorites=_max_int(records, "favorites"),
            genres=canonical_genres,
            studios=_merge_studios(records),
            licensors=_dedupe_strings(
                [value for record in records for value in record.licensors]
            ),
            source_materials=_dedupe_strings(
                [value for record in records for value in record.source_materials]
            ),
            broadcasts=_dedupe_strings(
                [value for record in records for value in record.broadcasts]
            ),
            titles_by_source=titles_by_source,
            synonyms_by_source=synonyms_by_source,
            staff_by_source=staff_by_source,
            voices_by_source=voices_by_source,
            descriptions=descriptions,
            background=_best_text(background_values),
            posters=_dedupe_strings(
                [value for record in records for value in record.posters]
            ),
            urls=urls,
            staff=_merge_people(
                [record.staff for record in records],
                drop_localization_roles=True,
            ),
            voices=_merge_people([record.voices for record in records]),
            errors=errors,
        )
