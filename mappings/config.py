from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parents[1]
load_dotenv(ROOT_DIR / ".env")


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


def _bool_env(name: str, default: bool) -> bool:
    raw = os.getenv(name, "1" if default else "0").strip().casefold()
    return raw not in {"", "0", "false", "no", "off"}


def _float_env(name: str, default: float, minimum: float = 0.0) -> float:
    raw = os.getenv(name, str(default)).strip()
    try:
        return max(minimum, float(raw))
    except ValueError:
        return float(default)


def mappings_db_path() -> Path:
    raw = os.getenv("MAPPINGS_DB_PATH", "data/mappings/mappings.db").strip()
    path = Path(raw or "data/mappings/mappings.db")
    return path if path.is_absolute() else ROOT_DIR / path


def mappings_auto_update() -> bool:
    return _bool_env("MAPPINGS_AUTO_UPDATE", True)


def mappings_keep_downloads() -> bool:
    return _bool_env("MAPPINGS_KEEP_DOWNLOADS", False)


def mappings_keep_previous() -> bool:
    return _bool_env("MAPPINGS_KEEP_PREVIOUS", True)


def mappings_update_max_age_hours() -> float:
    return _float_env("MAPPINGS_UPDATE_MAX_AGE_HOURS", 24.0, 0.25)


def mappings_request_timeout_seconds() -> float:
    return _float_env("MAPPINGS_REQUEST_TIMEOUT_SECONDS", 300.0, 30.0)


def mappings_check_interval_seconds() -> float:
    return _float_env("MAPPINGS_CHECK_INTERVAL_SECONDS", 3600.0, 300.0)
