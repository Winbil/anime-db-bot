from __future__ import annotations

import asyncio
import os
import re
import time
from dataclasses import dataclass

from core.contracts import AnimeSearchProvider
from core.models import SearchCandidate, SearchPage


@dataclass(slots=True)
class _CacheEntry:
    expires_at: float
    page: SearchPage


class SearchService:
    """Search through dedicated providers and merge their results by MAL ID."""

    def __init__(self, providers: tuple[AnimeSearchProvider, ...] | list[AnimeSearchProvider]) -> None:
        self._providers = tuple(providers)
        if not self._providers:
            raise ValueError("SearchService requires at least one search provider")

        self._cache: dict[tuple[str, int, int], _CacheEntry] = {}

    @property
    def provider_names(self) -> tuple[str, ...]:
        return tuple(provider.name for provider in self._providers)

    @property
    def provider_name(self) -> str:
        return ", ".join(self.provider_names)

    def _cache_ttl(self) -> int:
        raw = os.getenv("SEARCH_CACHE_TTL_SECONDS", "21600").strip()
        try:
            return max(0, int(raw))
        except ValueError:
            return 21600

    def _cache_max_entries(self) -> int:
        raw = os.getenv("SEARCH_CACHE_MAX_ENTRIES", "500").strip()
        try:
            return max(10, int(raw))
        except ValueError:
            return 500

    async def search(
        self,
        query: str,
        *,
        page: int = 1,
        page_size: int = 10,
    ) -> SearchPage:
        query = _normalize_query(query)
        page = max(1, int(page))
        page_size = max(1, int(page_size))

        cache_key = (query.casefold(), page, page_size)
        cached = self._cache.get(cache_key)
        now = time.monotonic()
        if cached is not None and cached.expires_at > now:
            return cached.page
        if cached is not None:
            self._cache.pop(cache_key, None)

        async def run(provider: AnimeSearchProvider):
            try:
                result = await provider.search(query, page=page, limit=page_size)
                return provider.name, result, None
            except Exception as exc:
                return provider.name, None, f"{type(exc).__name__}: {exc}"

        results = await asyncio.gather(*(run(provider) for provider in self._providers))
        merged = _merge_results(query, results, page=page, page_size=page_size)

        ttl = self._cache_ttl()
        if ttl > 0:
            self._cache[cache_key] = _CacheEntry(expires_at=now + ttl, page=merged)
            while len(self._cache) > self._cache_max_entries():
                oldest_key = next(iter(self._cache))
                self._cache.pop(oldest_key, None)

        return merged


def _merge_results(
    query: str,
    results: list[tuple[str, SearchPage | None, str | None]],
    *,
    page: int,
    page_size: int,
) -> SearchPage:
    use_russian_title = bool(re.search(r"[а-яё]", query, flags=re.IGNORECASE))
    preferred_provider = "Shikimori" if use_russian_title else "MyAnimeList"

    merged: dict[str, SearchCandidate] = {}
    rank: dict[str, tuple[int, int]] = {}
    errors: dict[str, str] = {}
    has_next = False

    for provider_index, (provider_name, provider_page, error) in enumerate(results):
        if error:
            errors[provider_name] = error
            continue
        if provider_page is None:
            continue

        has_next = has_next or provider_page.has_next

        for item_index, candidate in enumerate(provider_page.items):
            mal_id = candidate.external_ids.get("mal")
            if not mal_id:
                continue

            current = merged.get(mal_id)
            if current is None:
                merged[mal_id] = SearchCandidate(
                    title=candidate.title,
                    aliases=_dedupe(candidate.aliases),
                    year=candidate.year,
                    external_ids=dict(candidate.external_ids),
                    scores=dict(candidate.scores),
                )
                rank[mal_id] = (
                    0 if provider_name == preferred_provider else 1,
                    item_index,
                )
                continue

            old_title = current.title
            if provider_name == preferred_provider and candidate.title:
                current.title = candidate.title

            current.aliases = _dedupe(
                [
                    *current.aliases,
                    old_title,
                    candidate.title,
                    *candidate.aliases,
                ]
            )
            current.aliases = [
                value
                for value in current.aliases
                if value.casefold() != current.title.casefold()
            ]

            if current.year is None:
                current.year = candidate.year
            current.external_ids.update(
                {key: value for key, value in candidate.external_ids.items() if value}
            )
            current.scores.update(candidate.scores)

            candidate_rank = (
                0 if provider_name == preferred_provider else 1,
                item_index,
            )
            if candidate_rank < rank[mal_id]:
                rank[mal_id] = candidate_rank

    items = list(merged.values())
    items.sort(
        key=lambda item: (
            rank.get(item.external_ids.get("mal", ""), (9, 9999)),
            -len(item.scores),
            item.title.casefold(),
        )
    )

    return SearchPage(
        items=items,
        page=page,
        page_size=page_size,
        has_next=has_next,
        errors=errors,
    )


def _normalize_query(query: str) -> str:
    query = " ".join((query or "").split()).strip()
    return query.replace("Ё", "Е").replace("ё", "е")


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
