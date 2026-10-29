from __future__ import annotations

import logging
import time

from core.cache import BoundedTTLCache
from core.contracts import AnimeSearchProvider
from core.identity import AnimeIdentity
from mappings.resolver import MappingResolver
from search.providers.shikimori import ShikimoriSearchProvider

_CACHE_TTL_SECONDS = 21600.0
_NEGATIVE_CACHE_TTL_SECONDS = 1800.0


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


class IdentityResolver:
    """Owned cross-database identity enrichment service.

    Static enrichment is intentionally one-hop only through ``MappingResolver``.
    Shikimori remains a bounded live fallback for confirmed MAL IDs because the
    downloaded mapping datasets do not provide a useful Shikimori graph.
    """

    def __init__(
        self,
        *,
        mapping_resolver: MappingResolver | None = None,
        shikimori_provider: AnimeSearchProvider | None = None,
    ) -> None:
        self._mapping_resolver = mapping_resolver or MappingResolver()
        self._shikimori_provider = shikimori_provider or ShikimoriSearchProvider()
        self._shikimori_cache = BoundedTTLCache[str, str | None](
            max_entries=2000, name="identity_shikimori"
        )

    @property
    def mapping_resolver(self) -> MappingResolver:
        return self._mapping_resolver

    @property
    def shikimori_provider(self) -> AnimeSearchProvider:
        return self._shikimori_provider

    async def _resolve_shikimori_from_mal(
        self,
        mal_id: str,
        titles: list[str],
    ) -> str | None:
        try:
            return self._shikimori_cache[mal_id]
        except KeyError:
            pass

        for query in _dedupe(titles)[:5]:
            try:
                page = await self._shikimori_provider.search(query, page=1, limit=20)
            except Exception as exc:
                logging.warning(
                    "Live identity resolver query failed",
                    extra={
                        "event": "resolver_live_lookup",
                        "provider": "shikimori",
                        "operation": "identity_resolve",
                        "outcome": "error",
                        "error_type": type(exc).__name__,
                    },
                )
                continue

            for candidate in page.items:
                candidate_identity = candidate.identity
                if candidate_identity.get("mal") != mal_id:
                    continue
                shikimori_id = candidate_identity.get("shikimori")
                if shikimori_id and shikimori_id.isdigit():
                    self._shikimori_cache.set(
                        mal_id,
                        shikimori_id,
                        ttl_seconds=_CACHE_TTL_SECONDS,
                    )
                    return shikimori_id

        self._shikimori_cache.set(
            mal_id,
            None,
            ttl_seconds=_NEGATIVE_CACHE_TTL_SECONDS,
        )
        return None

    async def enrich(
        self,
        identity: AnimeIdentity,
        titles: list[str],
    ) -> AnimeIdentity:
        """Best-effort direct cross-database identity enrichment."""
        started = time.monotonic()
        enriched = identity.copy()
        accepted = 0
        conflict_count = 0

        mapped = self._mapping_resolver.resolve(enriched)
        if mapped:
            conflicts = enriched.merge_missing(mapped)
            if conflicts:
                conflict_count += len(conflicts)
                logging.warning(
                    "Resolver ignored conflicting mapping edges",
                    extra={
                        "event": "resolver_mapping",
                        "provider": "mappings_db",
                        "operation": "identity_resolve",
                        "outcome": "conflict",
                        "conflicts": len(conflicts),
                    },
                )
            additions = {
                provider: external_id
                for provider, external_id in mapped.items()
                if provider not in identity.external_ids
            }
            if additions:
                accepted += len(additions)
                logging.info(
                    "Identity enriched from mapping evidence",
                    extra={
                        "event": "resolver_mapping",
                        "provider": "mappings_db",
                        "operation": "identity_resolve",
                        "outcome": "accepted",
                        "accepted": len(additions),
                    },
                )

        if not enriched.has("shikimori"):
            mal_id = enriched.get("mal")
            if mal_id and mal_id.isdigit():
                shikimori_id = await self._resolve_shikimori_from_mal(mal_id, titles)
                if shikimori_id:
                    enriched.merge_missing({"shikimori": shikimori_id})
                    accepted += 1
                    logging.info(
                        "Identity enriched by live resolver",
                        extra={
                            "event": "resolver_live_lookup",
                            "provider": "shikimori",
                            "operation": "identity_resolve",
                            "outcome": "accepted",
                            "accepted": 1,
                        },
                    )

        logging.info(
            "Identity resolver completed",
            extra={
                "event": "resolver_lookup",
                "operation": "identity_resolve",
                "outcome": "success",
                "accepted": accepted,
                "conflicts": conflict_count,
                "size": len(enriched.external_ids),
                "duration_ms": round((time.monotonic() - started) * 1000, 3),
            },
        )
        return enriched
