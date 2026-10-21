from __future__ import annotations

import re
import unicodedata
from functools import lru_cache

from localization.catalog import DEFAULT_LOCALE, aliases, normalize_locale, text


CYRILLIC_RE = re.compile(r"[А-Яа-яЁё]")
LATIN_RE = re.compile(r"[A-Za-z]")
JAPANESE_RE = re.compile(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff]")
WORD_RE = re.compile(r"[^a-zа-яё0-9]+", re.IGNORECASE)
TRAILING_DETAILS_RE = re.compile(r"^(.*?)(\s*\([^)]*\))$")
VOICE_OF_PREFIX = "voice_of::"


LOCALIZATION_ROLE_MARKERS = (
    "adr",
    "dub director",
    "dub script",
    "dubbing",
    "mix engineer",
    "script supervisor",
)

LOCALIZATION_LANGUAGE_MARKERS = (
    "english",
    "brazilian portuguese",
    "latin american spanish",
    "portuguese",
    "spanish",
    "german",
    "italian",
    "french",
    "indonesian",
    "korean",
    "chinese",
)


RU_TO_LATIN = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e",
    "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "kh", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "shch",
    "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
}


def clean_text(value: str) -> str:
    return " ".join((value or "").split()).strip()


def normalize_key(value: str) -> str:
    value = clean_text(value).casefold().replace("ё", "е")

    normalized_parts: list[str] = []
    for char in value:
        if char == "й":
            normalized_parts.append(char)
            continue
        normalized_parts.extend(
            item
            for item in unicodedata.normalize("NFKD", char)
            if not unicodedata.combining(item)
        )
    value = "".join(normalized_parts)

    value = WORD_RE.sub(" ", value)
    return " ".join(value.split())


@lru_cache(maxsize=None)
def _normalized_aliases(section: str) -> dict[str, str]:
    return {
        normalize_key(alias): canonical
        for alias, canonical in aliases(section).items()
        if normalize_key(alias)
    }


@lru_cache(maxsize=None)
def _canonical_values(section: str) -> frozenset[str]:
    return frozenset(_normalized_aliases(section).values())


def transliterate_ru(value: str) -> str:
    result: list[str] = []
    for char in clean_text(value).casefold():
        result.append(RU_TO_LATIN.get(char, char))
    return "".join(result)


def contains_cyrillic(value: str) -> bool:
    return bool(CYRILLIC_RE.search(value or ""))


def canonical_genre_key(value: str) -> str | None:
    cleaned = clean_text(value)
    if not cleaned:
        return None
    normalized = normalize_key(cleaned)
    direct = _normalized_aliases("genres").get(normalized)
    if direct:
        return direct
    if cleaned in _canonical_values("genres"):
        return cleaned
    return None


def canonical_genre_token(value: str) -> str:
    cleaned = clean_text(value)
    if not cleaned:
        return ""
    return canonical_genre_key(cleaned) or cleaned


def canonical_genre(value: str, *, locale: str = DEFAULT_LOCALE) -> str:
    cleaned = clean_text(value)
    if not cleaned:
        return ""
    key = canonical_genre_key(cleaned)
    return text("genres", key, locale=locale, default=cleaned) if key else cleaned


def _role_base_and_suffix(value: str) -> tuple[str, str]:
    cleaned = clean_text(value)
    if not cleaned:
        return "", ""
    match = TRAILING_DETAILS_RE.match(cleaned)
    if match:
        return clean_text(match.group(1)), match.group(2)
    return cleaned, ""


def canonical_role_key(value: str) -> str | None:
    base, _ = _role_base_and_suffix(value)
    if not base:
        return None
    normalized = normalize_key(base)
    direct = _normalized_aliases("roles").get(normalized)
    if direct:
        return direct
    if base in _canonical_values("roles"):
        return base
    return None


def canonical_role_token(value: str) -> str:
    cleaned = clean_text(value)
    if not cleaned:
        return ""
    if cleaned.startswith(VOICE_OF_PREFIX):
        return cleaned
    base, suffix = _role_base_and_suffix(cleaned)
    key = canonical_role_key(base)
    return f"{key}{suffix}" if key else cleaned


def voice_role_token(character_name: str | None = None) -> str:
    character = clean_text(character_name or "")
    return f"{VOICE_OF_PREFIX}{character}" if character else "voice_actor"


def localize_role_token(value: str, *, locale: str = DEFAULT_LOCALE) -> str:
    cleaned = clean_text(value)
    if not cleaned:
        return ""
    if cleaned.startswith(VOICE_OF_PREFIX):
        character = cleaned.removeprefix(VOICE_OF_PREFIX)
        return text("common", "voice_of", locale=locale, name=character)

    base, suffix = _role_base_and_suffix(cleaned)
    if base in _canonical_values("roles"):
        translated = text("roles", base, locale=locale, default=base)
        return f"{translated}{suffix}"
    return canonical_role(cleaned, locale=locale)


def canonical_role(value: str, *, locale: str = DEFAULT_LOCALE) -> str:
    cleaned = clean_text(value)
    if not cleaned:
        return ""

    base, suffix = _role_base_and_suffix(cleaned)
    key = canonical_role_key(base)
    if key:
        translated = text("roles", key, locale=locale, default=base)
        return f"{translated}{suffix}"
    return cleaned


def studio_identity_key(value: str) -> str:
    return normalize_key(value).replace(" ", "")


@lru_cache(maxsize=1)
def _studio_aliases() -> dict[str, str]:
    return {
        studio_identity_key(alias): canonical
        for alias, canonical in aliases("studios").items()
        if studio_identity_key(alias)
    }


def canonical_studio_key(value: str) -> str | None:
    cleaned = clean_text(value)
    if not cleaned:
        return None
    return _studio_aliases().get(studio_identity_key(cleaned))


def canonical_studio(value: str, *, locale: str = DEFAULT_LOCALE) -> str:
    cleaned = clean_text(value)
    if not cleaned:
        return ""
    key = canonical_studio_key(cleaned)
    return text("studios", key, locale=locale, default=cleaned) if key else cleaned


def is_localization_role(value: str) -> bool:
    normalized = normalize_key(value)
    if not normalized:
        return False
    if any(marker in normalized for marker in LOCALIZATION_ROLE_MARKERS):
        return True
    return any(marker in normalized for marker in LOCALIZATION_LANGUAGE_MARKERS)


def is_primary_voice_role(value: str) -> bool:
    base, suffix = _role_base_and_suffix(value)
    if suffix:
        return False
    return canonical_role_key(base) == "voice_actor"


def person_identity_keys(names: list[str]) -> set[str]:
    keys: set[str] = set()
    for name in names:
        name = clean_text(name)
        if not name or normalize_key(name) in {"неизвестно", "unknown"}:
            continue

        direct = normalize_key(name)
        if direct:
            keys.add(direct)
            tokens = direct.split()
            if len(tokens) >= 2:
                keys.add(" ".join(sorted(tokens)))

        transliterated = normalize_key(transliterate_ru(name))
        if transliterated:
            keys.add(transliterated)
            tokens = transliterated.split()
            if len(tokens) >= 2:
                keys.add(" ".join(sorted(tokens)))
    return keys


def preferred_person_name(names: list[str], *, locale: str = DEFAULT_LOCALE) -> str:
    locale = normalize_locale(locale)
    unique: list[str] = []
    seen: set[str] = set()
    for value in names:
        value = clean_text(value)
        key = normalize_key(value)
        if value and key and key not in seen:
            seen.add(key)
            unique.append(value)

    if not unique:
        return text("common", "unknown", locale=locale, default="Unknown")

    cyrillic = [value for value in unique if contains_cyrillic(value)]
    latin = [
        value
        for value in unique
        if LATIN_RE.search(value) and not CYRILLIC_RE.search(value) and not JAPANESE_RE.search(value)
    ]

    preferred_groups = (latin, cyrillic) if locale == "en" else (cyrillic, latin)
    for group in preferred_groups:
        if group:
            return min(group, key=lambda value: (len(value), value.casefold()))

    return min(unique, key=lambda value: (len(value), value.casefold()))


def display_person_name(
    name: str,
    aliases_values: list[str],
    *,
    locale: str = DEFAULT_LOCALE,
) -> str:
    locale = normalize_locale(locale)
    names = [name, *aliases_values]
    primary = preferred_person_name(names, locale=locale)
    if not primary:
        return text("common", "unknown", locale=locale, default="Unknown")

    unique: list[str] = []
    seen: set[str] = set()
    for value in names:
        cleaned = clean_text(value)
        key = normalize_key(cleaned)
        if cleaned and key and key not in seen:
            seen.add(key)
            unique.append(cleaned)

    extras: list[str] = []
    japanese = next(
        (value for value in unique if normalize_key(value) != normalize_key(primary) and JAPANESE_RE.search(value)),
        None,
    )
    latin = next(
        (
            value
            for value in unique
            if normalize_key(value) != normalize_key(primary)
            and LATIN_RE.search(value)
            and not CYRILLIC_RE.search(value)
            and not JAPANESE_RE.search(value)
        ),
        None,
    )

    if locale == "ru" and CYRILLIC_RE.search(primary) and latin:
        extras.append(latin)
    if japanese:
        extras.append(japanese)

    return f"{primary} ({', '.join(extras)})" if extras else primary
