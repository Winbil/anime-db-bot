from __future__ import annotations

from pathlib import Path

from core.settings import get_settings


def mappings_db_path() -> Path:
    return get_settings().mappings.db_path


def mappings_manifest_path() -> Path:
    return get_settings().mappings.manifest_path


def mappings_release_repository() -> str:
    return get_settings().mappings.release_repository


def mappings_auto_update() -> bool:
    return get_settings().mappings.auto_update


def mappings_keep_previous() -> bool:
    return get_settings().mappings.keep_previous


def mappings_request_timeout_seconds() -> float:
    return get_settings().mappings.request_timeout_seconds


def mappings_check_interval_seconds() -> float:
    return get_settings().mappings.check_interval_seconds
