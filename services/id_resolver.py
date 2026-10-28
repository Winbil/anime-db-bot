from __future__ import annotations

import logging

from core.cache import BoundedTTLCache
from core.identity import AnimeIdentity
from mappings.resolver import MAPPING_RESOLVER
from search.providers.shikimori import ShikimoriSearchProvider


_SHIKIMORI_RESOLVER = ShikimoriSearchProvider()
_CACHE_TTL_SECONDS = 21600.0
_NEGATIVE_CACHE_TTL_SECONDS = 1800.0
_CACHE = BoundedTTLCache[str, str | None](max_entries=2000)


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
    try:
        return _CACHE[mal_id]
    except KeyError:
        pass

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
                _CACHE.set(mal_id, shikimori_id, ttl_seconds=_CACHE_TTL_SECONDS)
                return shikimori_id

    _CACHE.set(mal_id, None, ttl_seconds=_NEGATIVE_CACHE_TTL_SECONDS)
    return None


async def enrich_identity(
    identity: AnimeIdentity,
    titles: list[str],
) -> AnimeIdentity:
    """Best-effort cross-database identity enrichment.

    The first layer uses only direct, accepted mappings from source-confirmed IDs
    in the disk-backed ``mappings.db``. Arbitrary transitive chains are deliberately
    forbidden because TVDB/TMDB/AniDB/MAL can split seasons and specials differently.
    Shikimori remains a live fallback because the external mapping datasets do not
    provide a useful Shikimori cross-ID graph.
    """
    enriched = identity.copy()

    mapped = MAPPING_RESOLVER.resolve(enriched)
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
