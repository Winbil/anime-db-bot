from __future__ import annotations

import json
from functools import lru_cache
from importlib import resources
from typing import Any

DEFAULT_LOCALE = "ru"


@lru_cache(maxsize=None)
def _load_json(relative_path: str) -> dict[str, Any]:
    package_root = resources.files("localization")
    resource = package_root.joinpath(*relative_path.split("/"))
    data = json.loads(resource.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise RuntimeError(f"Localization resource {relative_path} must contain a JSON object")
    return data


@lru_cache(maxsize=1)
def _aliases_catalog() -> dict[str, Any]:
    return _load_json("data/aliases.json")


@lru_cache(maxsize=1)
def _source_catalog() -> dict[str, Any]:
    return _load_json("data/source_values.json")


@lru_cache(maxsize=None)
def _locale_catalog(locale: str) -> dict[str, Any]:
    locale = (locale or DEFAULT_LOCALE).strip().lower() or DEFAULT_LOCALE
    try:
        return _load_json(f"locales/{locale}.json")
    except FileNotFoundError:
        if locale == DEFAULT_LOCALE:
            raise
        return _load_json(f"locales/{DEFAULT_LOCALE}.json")


def available_locales() -> tuple[str, ...]:
    locale_dir = resources.files("localization").joinpath("locales")
    return tuple(
        sorted(
            item.name.removesuffix(".json")
            for item in locale_dir.iterdir()
            if item.is_file() and item.name.endswith(".json")
        )
    )


def aliases(section: str) -> dict[str, str]:
    raw = _aliases_catalog().get(section, {})
    if not isinstance(raw, dict):
        raise RuntimeError(f"Localization alias section {section!r} must be an object")
    return {
        str(key): str(value)
        for key, value in raw.items()
        if str(key).strip() and str(value).strip()
    }


def text(
    section: str,
    key: str,
    *,
    locale: str = DEFAULT_LOCALE,
    default: str | None = None,
    **params: object,
) -> str:
    section_map = _locale_catalog(locale).get(section, {})
    value: object | None = None
    if isinstance(section_map, dict):
        value = section_map.get(key)

    if value is None and locale != DEFAULT_LOCALE:
        fallback_section = _locale_catalog(DEFAULT_LOCALE).get(section, {})
        if isinstance(fallback_section, dict):
            value = fallback_section.get(key)

    if value is None:
        value = default if default is not None else key

    result = str(value)
    if params:
        try:
            result = result.format(**params)
        except (KeyError, ValueError):
            pass
    return result


def _source_field(source: str, field: str) -> tuple[str, dict[str, str]] | None:
    source_data = _source_catalog().get(source, {})
    if not isinstance(source_data, dict):
        return None
    field_data = source_data.get(field, {})
    if not isinstance(field_data, dict):
        return None

    domain = str(field_data.get("domain") or "").strip()
    values = field_data.get("values", {})
    if not domain or not isinstance(values, dict):
        return None
    return domain, {str(key): str(value) for key, value in values.items()}


def source_canonical_key(source: str, field: str, value: object) -> tuple[str, str] | None:
    mapping = _source_field(source, field)
    raw = str(value or "").strip()
    if mapping is None or not raw:
        return None

    domain, values = mapping
    canonical = values.get(raw)
    if canonical is None:
        folded = raw.casefold()
        canonical = next(
            (mapped for candidate, mapped in values.items() if candidate.casefold() == folded),
            None,
        )
    if canonical is None:
        return None
    return domain, canonical


def localize_source_value(
    source: str,
    field: str,
    value: object,
    *,
    locale: str = DEFAULT_LOCALE,
    default: str | None = None,
) -> str | None:
    raw = str(value or "").strip()
    if not raw:
        return default

    canonical = source_canonical_key(source, field, raw)
    if canonical is None:
        return raw if default is None else default

    domain, key = canonical
    return text(domain, key, locale=locale, default=raw)
