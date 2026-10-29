from __future__ import annotations

from collections.abc import Mapping
from typing import TypeVar

from core.models import AggregatedAnime
from sources.runtime.catalog import source_key_for_display_name

T = TypeVar("T")


def ordered_mapping_items(
    mapping: Mapping[str, T],
    source_order: list[str],
) -> list[tuple[str, T]]:
    result: list[tuple[str, T]] = []
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
    elif section == "screenshots":
        available = {
            source
            for source, screenshots in anime.screenshots_by_source.items()
            if screenshots
        }
    else:
        return []

    ordered = [source for source in anime.sources if source in available]
    ordered.extend(sorted(available - set(ordered)))
    return ordered


def description_sources(anime: AggregatedAnime) -> list[str]:
    available = set(anime.descriptions) | set(anime.backgrounds_by_source)
    ordered = [source for source in anime.sources if source in available]
    ordered.extend(sorted(available - set(ordered)))
    return ordered


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
