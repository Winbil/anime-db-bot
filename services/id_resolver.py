from __future__ import annotations

import logging
import time

from search.providers.shikimori import ShikimoriSearchProvider


_RESOLVER = ShikimoriSearchProvider()
_CACHE_TTL_SECONDS = 21600.0
_NEGATIVE_CACHE_TTL_SECONDS = 1800.0
_CACHE: dict[str, tuple[float, str | None]] = {}


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        value = " ".join((value or "").split()).strip()
        key = value.casefold()
        if value and key not in seen:
            seen.add(key)
            result.append(value)
    return result


async def resolve_shikimori_id(
    mal_id: str,
    titles: list[str],
) -> str | None:
    """Resolve MAL -> Shikimori without coupling metadata sources to text search.

    Default /anime results already carry a Shikimori ID because Shikimori is
    one of the search providers. This fallback exists for explicit MAL-only or
    AniList-only searches: it searches Shikimori only until it finds a result
    whose MAL ID exactly matches the already-selected anime.
    """
    mal_id = str(mal_id or "").strip()
    if not mal_id.isdigit():
        return None

    now = time.monotonic()
    cached = _CACHE.get(mal_id)
    if cached is not None and cached[0] > now:
        return cached[1]
    if cached is not None:
        _CACHE.pop(mal_id, None)

    queries = _dedupe(titles)[:5]
    for query in queries:
        try:
            page = await _RESOLVER.search(query, page=1, limit=20)
        except Exception:
            logging.warning(
                "Could not resolve Shikimori ID for MAL %s via query %r",
                mal_id,
                query,
                exc_info=True,
            )
            continue

        for candidate in page.items:
            if str(candidate.external_ids.get("mal") or "").strip() != mal_id:
                continue
            shikimori_id = str(
                candidate.external_ids.get("shikimori") or ""
            ).strip()
            if shikimori_id.isdigit():
                _CACHE[mal_id] = (
                    time.monotonic() + _CACHE_TTL_SECONDS,
                    shikimori_id,
                )
                logging.info(
                    "Resolved Shikimori ID %s for MAL %s",
                    shikimori_id,
                    mal_id,
                )
                return shikimori_id

    _CACHE[mal_id] = (
        time.monotonic() + _NEGATIVE_CACHE_TTL_SECONDS,
        None,
    )
    return None
