from __future__ import annotations

from enum import StrEnum


class SourceKey(StrEnum):
    """Stable identity/database keys used across the application.

    The enum subclasses ``str`` so existing serialized callback/database payloads
    remain backward compatible while new code gets a single typed vocabulary.
    Jikan deliberately does not appear here: it is a MAL backend, not an identity.
    """

    SHIKIMORI = "shikimori"
    MAL = "mal"
    ANILIST = "anilist"
    KITSU = "kitsu"
    ANIDB = "anidb"
    ANISEARCH = "anisearch"
    IMDB = "imdb"


def normalize_source_key(value: SourceKey | str) -> SourceKey:
    raw = str(value or "").strip().casefold()
    try:
        return SourceKey(raw)
    except ValueError as exc:
        raise ValueError(f"Unknown source key: {value!r}") from exc
