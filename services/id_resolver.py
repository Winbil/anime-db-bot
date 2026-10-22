from __future__ import annotations

import logging
import time

from core.identity import AnimeIdentity
from search.providers.shikimori import ShikimoriSearchProvider


_SHIKIMORI_RESOLVER = ShikimoriSearchProvider()
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


async def _resolve_shikimori_from_mal(
    mal_id: str,
    titles: list[str],
) -> str | None:
    now = time.monotonic()
    cached = _CACHE.get(mal_id)
    if cached is not None and cached[0] > now:
        return cached[1]
    if cached is not None:
        _CACHE.pop(mal_id, None)

    for query in _dedupe(titles)[:5]:
        try:
            page = await _SHIKIMORI_RESOLVER.search(query, page=1, limit=20)
        except Exception:
            logging.warning(
                "Could not resolve Shikimori ID from MAL %s via query %r",
                mal_id,
                query,
                exc_info=True,
            )
            continue

        for candidate in page.items:
            candidate_identity = candidate.identity
            if candidate_identity.get("mal") != mal_id:
                continue
            shikimori_id = candidate_identity.get("shikimori")
            if shikimori_id and shikimori_id.isdigit():
                _CACHE[mal_id] = (
                    time.monotonic() + _CACHE_TTL_SECONDS,
                    shikimori_id,
                )
                return shikimori_id

    _CACHE[mal_id] = (time.monotonic() + _NEGATIVE_CACHE_TTL_SECONDS, None)
    return None


async def enrich_identity(
    identity: AnimeIdentity,
    titles: list[str],
) -> AnimeIdentity:
    """Best-effort cross-database identity enrichment.

    Resolvers add optional edges to the identity graph; none of them is a global
    primary-key rule. The first resolver is MAL -> Shikimori only because
    Shikimori search currently exposes both IDs. Future resolvers can add other
    directions without changing source contracts.
    """
    enriched = identity.copy()

    if not enriched.has("shikimori"):
        mal_id = enriched.get("mal")
        if mal_id and mal_id.isdigit():
            shikimori_id = await _resolve_shikimori_from_mal(mal_id, titles)
            if shikimori_id:
                enriched.merge_missing({"shikimori": shikimori_id})
                logging.info(
                    "Identity enriched with shikimori:%s from mal:%s",
                    shikimori_id,
                    mal_id,
                )

    return enriched
