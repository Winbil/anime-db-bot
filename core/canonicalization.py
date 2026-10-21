from __future__ import annotations

import re
import unicodedata
from functools import lru_cache

from localization.catalog import DEFAULT_LOCALE, aliases, text


CYRILLIC_RE = re.compile(r"[А-Яа-яЁё]")
WORD_RE = re.compile(r"[^a-zа-яё0-9]+", re.IGNORECASE)
TRAILING_DETAILS_RE = re.compile(r"^(.*?)(\s*\([^)]*\))$")


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

    # NFKD is useful for accent-insensitive Latin matching, but Cyrillic "й"
    # decomposes into "и" + COMBINING BREVE. Dropping all combining marks would
    # therefore silently turn "й" into "и" (for example "сэйю" -> "сэию").
    # Preserve "й" explicitly while still stripping Latin diacritics.
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
    return _normalized_aliases("genres").get(normalize_key(cleaned))


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
    return _normalized_aliases("roles").get(normalize_key(base))


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
    # Studio names frequently differ only by punctuation: 8bit / 8-bit,
    # A-1 Pictures / A1 Pictures, etc.
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
    # AniList often annotates localization credits with the language in the
    # role text, e.g. "ADR Director (English)".
    return any(marker in normalized for marker in LOCALIZATION_LANGUAGE_MARKERS)


def is_primary_voice_role(value: str) -> bool:
    """Return True only for original/Japanese voice acting roles.

    Shikimori distinguishes foreign dubs as "Сэйю (EN)", "Сэйю (DE)", etc.
    Those should not be mixed into the main seiyuu list.
    """
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

    # Prefer a clean Russian display name over an old combined Shikimori string
    # like "Ёхэй Ито (Youhei Itou, 伊藤 洋平)".
    cyrillic = [value for value in unique if contains_cyrillic(value)]
    if cyrillic:
        return min(cyrillic, key=lambda value: (len(value), value.casefold()))

    ascii_names = [value for value in unique if value.isascii()]
    if ascii_names:
        return min(ascii_names, key=lambda value: (len(value), value.casefold()))

    return min(unique, key=lambda value: (len(value), value.casefold()))
