from __future__ import annotations

import logging
import time

from core.identity import AnimeIdentity
from mappings.database import MAPPING_DATABASE
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

    The first layer is the local disk-backed mapping graph. It can add only
    unambiguous accepted edges from ``mappings.db`` and never overwrites an ID
    already confirmed by a source. Shikimori remains a live fallback because the
    external mapping datasets do not provide a useful Shikimori cross-ID graph.
    """
    enriched = identity.copy()

    mapped = MAPPING_DATABASE.resolve(enriched)
    if mapped:
        conflicts = enriched.merge_missing(mapped)
        if conflicts:
            logging.warning("Ignoring conflicting mappings.db edges: %s", conflicts)
        additions = {
            provider: external_id
            for provider, external_id in mapped.items()
            if provider not in identity.external_ids
        }
        if additions:
            logging.info("Identity enriched from mappings.db: %s", additions)

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
