from __future__ import annotations

from core.models import AggregatedAnime, PersonCredit

PEOPLE_SECTIONS = frozenset({"staff", "voices"})


def section_mapping(
    anime: AggregatedAnime,
    section: str,
) -> dict[str, list[PersonCredit]]:
    if section == "staff":
        return anime.staff_by_source
    if section == "voices":
        return anime.voices_by_source
    return {}


def all_people(anime: AggregatedAnime, section: str) -> list[PersonCredit]:
    if section == "staff":
        return anime.staff
    if section == "voices":
        return anime.voices
    return []


def dedupe_strings(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        cleaned = " ".join((value or "").split()).strip()
        key = cleaned.casefold()
        if cleaned and key not in seen:
            seen.add(key)
            result.append(cleaned)
    return result


def portrait_urls(
    person: PersonCredit,
    *,
    source: str | None = None,
    source_order: list[str] | None = None,
) -> list[str]:
    if source is not None:
        return dedupe_strings(list(person.portraits.get(source, [])))
    result: list[str] = []
    seen_sources: set[str] = set()
    for source_name in source_order or []:
        seen_sources.add(source_name)
        result.extend(person.portraits.get(source_name, []))
    for source_name, urls in person.portraits.items():
        if source_name not in seen_sources:
            result.extend(urls)
    return dedupe_strings(result)


def portrait_source_names(person: PersonCredit, source_order: list[str]) -> list[str]:
    available = {
        source
        for source, urls in person.portraits.items()
        if dedupe_strings(list(urls or []))
    }
    ordered = [source for source in source_order if source in available]
    ordered.extend(sorted(available - set(ordered)))
    return ordered


def sources_with_portraits(anime: AggregatedAnime, section: str) -> list[str]:
    mapping = section_mapping(anime, section)
    available = {
        source
        for source, people in mapping.items()
        if any(portrait_urls(person, source=source) for person in people)
    }
    ordered = [source for source in anime.sources if source in available]
    ordered.extend(sorted(available - set(ordered)))
    return ordered


def people_for_scope(
    anime: AggregatedAnime,
    section: str,
    source: str | None,
) -> list[PersonCredit]:
    if source is None:
        return all_people(anime, section)
    return section_mapping(anime, section).get(source, [])


def people_state(
    anime: AggregatedAnime,
    section: str,
    source: str | None,
) -> tuple[list[PersonCredit], list[PersonCredit]]:
    without: list[PersonCredit] = []
    with_portraits: list[PersonCredit] = []
    for person in people_for_scope(anime, section, source):
        urls = portrait_urls(person, source=source, source_order=anime.sources)
        (with_portraits if urls else without).append(person)
    return without, with_portraits


def first_people_page(
    without: list[PersonCredit],
    with_portraits: list[PersonCredit],
) -> int:
    return 0 if without or not with_portraits else 1
