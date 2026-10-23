from __future__ import annotations

import asyncio
import os
import re

from core.canonicalization import normalize_key
from core.models import SearchCandidate, SearchResultSet
from services.direct_lookup import DirectIdLookupService
from services.search import SearchService, merge_candidates

_CYRILLIC_RE = re.compile(r"[а-яё]", flags=re.IGNORECASE)
_LATIN_RE = re.compile(r"[a-z]", flags=re.IGNORECASE)


def _env_int(
    name: str,
    default: int,
    *,
    minimum: int,
    maximum: int,
) -> int:
    raw = os.getenv(name, str(default)).strip()
    try:
        value = int(raw)
    except ValueError:
        value = default
    return min(max(value, minimum), maximum)


def _clean(value: str) -> str:
    return " ".join((value or "").split()).strip()


def _query_key(value: str) -> str:
    value = _clean(value)
    return normalize_key(value) or value.casefold()


def _dedupe(values) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for raw in values:
        value = _clean(str(raw or ""))
        key = _query_key(value)
        if value and key and key not in seen:
            seen.add(key)
            result.append(value)
    return result


def expansion_queries(
    query: str,
    candidates: list[SearchCandidate],
    *,
    limit: int = 1,
) -> list[str]:
    """Choose a small set of confirmed alternate-title queries.

    Opposite-script variants are preferred because they bridge providers that do
    not search the user's input language. Same-script aliases are only a fallback.
    Values come exclusively from source-returned candidates or metadata records;
    this function never translates or invents a title.
    """
    limit = max(0, int(limit))
    if limit == 0:
        return []

    original_key = _query_key(query)
    original_has_cyrillic = bool(_CYRILLIC_RE.search(query or ""))
    original_has_latin = bool(_LATIN_RE.search(query or ""))

    values: list[str] = []
    for candidate in candidates:
        values.extend([
            candidate.title,
            candidate.romaji_title or "",
            *candidate.aliases,
        ])

    opposite: list[str] = []
    fallback: list[str] = []
    for value in _dedupe(values):
        if _query_key(value) == original_key:
            continue
        has_cyrillic = bool(_CYRILLIC_RE.search(value))
        has_latin = bool(_LATIN_RE.search(value))

        if original_has_cyrillic and has_latin and not has_cyrillic:
            opposite.append(value)
        elif original_has_latin and has_cyrillic and not has_latin:
            opposite.append(value)
        elif not original_has_cyrillic and not original_has_latin and (has_latin or has_cyrillic):
            opposite.append(value)
        else:
            fallback.append(value)

    return (opposite + fallback)[:limit]


async def expand_text_search(
    *,
    service: SearchService,
    direct_lookup: DirectIdLookupService,
    query: str,
    initial: SearchResultSet,
) -> SearchResultSet:
    """Add bounded cross-language results without replacing primary ranking."""
    if not initial.items:
        return initial

    max_seeds = _env_int("SEARCH_EXPANSION_MAX_SEEDS", 1, minimum=0, maximum=3)
    max_queries = _env_int("SEARCH_EXPANSION_MAX_QUERIES", 1, minimum=0, maximum=3)
    max_pages = _env_int("SEARCH_EXPANSION_MAX_PAGES", 2, minimum=1, maximum=4)
    max_items = _env_int("SEARCH_COLLECTION_MAX_ITEMS", 120, minimum=10, maximum=1000)
    if max_seeds == 0 or max_queries == 0:
        return initial

    seed_items = list(initial.items[:max_seeds])
    queries = expansion_queries(query, seed_items, limit=max_queries)
    enriched_seeds: list[SearchCandidate] = []

    # Search providers such as Shikimori already return multiple title variants.
    # Reuse those first: there is no reason to fetch full metadata merely to
    # rediscover an alias we already have. Metadata identity expansion is only a
    # fallback when the first search set has no useful alternate-language title.
    if not queries:
        async def enrich(candidate: SearchCandidate) -> SearchCandidate:
            try:
                return await direct_lookup.enrich_candidate(candidate)
            except Exception:
                # Expansion is optional discovery. A failure must not discard the
                # already valid primary search result set.
                return candidate

        enriched_seeds = list(
            await asyncio.gather(*(enrich(item) for item in seed_items))
        )
        queries = expansion_queries(query, enriched_seeds, limit=max_queries)

    if not queries:
        merged = merge_candidates(
            [*initial.items, *enriched_seeds],
            query=query,
            allow_title_merge=True,
        )
        return SearchResultSet(
            items=merged[:max_items],
            complete=initial.complete and len(merged) <= max_items,
            errors=dict(initial.errors),
        )

    expanded_sets = await asyncio.gather(
        *(service.collect(value, max_pages=max_pages) for value in queries)
    )

    candidates: list[SearchCandidate] = [*initial.items, *enriched_seeds]
    errors = dict(initial.errors)
    complete = initial.complete
    for result_set in expanded_sets:
        candidates.extend(result_set.items)
        complete = complete and result_set.complete
        for source, error in result_set.errors.items():
            errors.setdefault(source, error)

    merged = merge_candidates(
        candidates,
        query=query,
        allow_title_merge=True,
    )
    if len(merged) > max_items:
        merged = merged[:max_items]
        complete = False

    return SearchResultSet(
        items=merged,
        complete=complete and not errors,
        errors=errors,
    )