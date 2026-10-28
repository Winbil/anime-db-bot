from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from core.settings import get_settings


@dataclass(frozen=True, slots=True)
class MappingSourceSpec:
    name: str
    url: str
    importer: str
    required: bool
    license_note: str
    checksum_url: str | None = None


SOURCE_SPECS: tuple[MappingSourceSpec, ...] = (
    MappingSourceSpec(
        name="Fribb/anime-lists",
        url="https://raw.githubusercontent.com/Fribb/anime-lists/master/anime-list-full.json",
        importer="fribb",
        required=True,
        license_note="No explicit repository dataset license; runtime download only.",
    ),
    MappingSourceSpec(
        name="Kometa-Team/Anime-IDs",
        url="https://raw.githubusercontent.com/Kometa-Team/Anime-IDs/master/anime_ids.json",
        importer="kometa",
        required=True,
        license_note="Repository MIT; generated data contains upstream mappings.",
    ),
    MappingSourceSpec(
        name="Anime-Lists/anime-lists",
        url="https://raw.githubusercontent.com/Anime-Lists/anime-lists/master/anime-list-full.xml",
        importer="anime_lists",
        required=True,
        license_note="No explicit repository dataset license; runtime download only.",
    ),
    MappingSourceSpec(
        name="cplieger/animap",
        url="https://github.com/cplieger/animap/releases/latest/download/animap.json",
        importer="animap",
        required=True,
        license_note="ODbL-1.0 + DbCL-1.0 data; Apache-2.0 code.",
        checksum_url="https://github.com/cplieger/animap/releases/latest/download/animap.json.sha256",
    ),
    MappingSourceSpec(
        name="manami-project/anime-offline-database",
        url="https://github.com/manami-project/anime-offline-database/releases/latest/download/anime-offline-database.jsonl",
        importer="manami",
        required=False,
        license_note="ODbL-1.0 + DbCL-1.0.",
    ),
    MappingSourceSpec(
        name="anibridge/anibridge-mappings",
        url="https://github.com/anibridge/anibridge-mappings/releases/download/v3/mappings.min.json",
        importer="anibridge",
        required=False,
        license_note="MIT repository; generated mapping data inherits upstream obligations.",
    ),
)


def mappings_db_path() -> Path:
    return get_settings().mappings.db_path


def mappings_auto_update() -> bool:
    return get_settings().mappings.auto_update


def mappings_keep_downloads() -> bool:
    return get_settings().mappings.keep_downloads


def mappings_keep_previous() -> bool:
    return get_settings().mappings.keep_previous


def mappings_update_max_age_hours() -> float:
    return get_settings().mappings.update_max_age_hours


def mappings_request_timeout_seconds() -> float:
    return get_settings().mappings.request_timeout_seconds


def mappings_check_interval_seconds() -> float:
    return get_settings().mappings.check_interval_seconds
