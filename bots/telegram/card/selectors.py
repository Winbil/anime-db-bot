from __future__ import annotations

from core.capabilities import source_key_for_display_name
from core.models import AggregatedAnime


def ordered_mapping_items(
    mapping: dict[str, object],
    source_order: list[str],
) -> list[tuple[str, object]]:
    result: list[tuple[str, object]] = []
    seen: set[str] = set()
    for source in source_order:
        if source in mapping:
            result.append((source, mapping[source]))
            seen.add(source)
    for source, value in mapping.items():
        if source not in seen:
            result.append((source, value))
    return result


def source_section_sources(anime: AggregatedAnime, section: str) -> list[str]:
    if section == "titles":
        available = {
            source
            for source in set(anime.titles_by_source) | set(anime.synonyms_by_source)
            if anime.titles_by_source.get(source)
            or anime.synonyms_by_source.get(source)
        }
    elif section == "staff":
        available = {
            source for source, people in anime.staff_by_source.items() if people
        }
    elif section == "voices":
        available = {
            source for source, people in anime.voices_by_source.items() if people
        }
    elif section == "popularity":
        available = {
            source
            for source, stats in anime.popularity_by_source.items()
            if stats.has_data()
        }
    else:
        return []

    ordered = [source for source in anime.sources if source in available]
    ordered.extend(sorted(available - set(ordered)))
    return ordered


def description_sources(anime: AggregatedAnime) -> list[str]:
    return [
        source for source, _ in ordered_mapping_items(anime.descriptions, anime.sources)
    ]


def source_options(source_names: list[str]) -> list[tuple[str, str]]:
    result: list[tuple[str, str]] = []
    seen: set[str] = set()
    for source_name in source_names:
        source_key = source_key_for_display_name(source_name)
        key = str(source_key) if source_key is not None else ""
        if key and key not in seen:
            seen.add(key)
            result.append((key, source_name))
    return result


def source_section_options(
    anime: AggregatedAnime,
    section: str,
) -> list[tuple[str, str]]:
    return source_options(source_section_sources(anime, section))


def description_source_options(anime: AggregatedAnime) -> list[tuple[str, str]]:
    return source_options(description_sources(anime))
