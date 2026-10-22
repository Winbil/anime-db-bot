from __future__ import annotations

import asyncio
import os
import re
import time
from dataclasses import dataclass

from core.contracts import AnimeSearchProvider
from core.identity import AnimeIdentity
from core.models import SearchCandidate, SearchPage


@dataclass(slots=True)
class _CacheEntry:
    expires_at: float
    page: SearchPage


class SearchService:
    """Search dedicated providers and merge results by shared external IDs."""

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
            self._cache.pop(cache_key, None)
            self._cache[cache_key] = cached
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
        if ttl > 0 and not merged.errors:
            self._cache[cache_key] = _CacheEntry(
                expires_at=time.monotonic() + ttl,
                page=merged,
            )
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

    entries: list[tuple[int, str, int, SearchCandidate]] = []
    errors: dict[str, str] = {}
    provider_has_next = False

    for provider_index, (provider_name, provider_page, error) in enumerate(results):
        if error:
            errors[provider_name] = error
            continue
        if provider_page is None:
            continue
        provider_has_next = provider_has_next or provider_page.has_next
        entries.extend(
            (provider_index, provider_name, item_index, candidate)
            for item_index, candidate in enumerate(provider_page.items)
        )

    parent = list(range(len(entries)))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(left: int, right: int) -> None:
        left_root = find(left)
        right_root = find(right)
        if left_root != right_root:
            parent[right_root] = left_root

    identities = [candidate.identity for _, _, _, candidate in entries]
    for right in range(len(entries)):
        if identities[right].is_empty():
            continue
        for left in range(right):
            if identities[left].matches(identities[right]):
                union(left, right)

    groups: dict[int, list[tuple[int, str, int, SearchCandidate]]] = {}
    for index, entry in enumerate(entries):
        groups.setdefault(find(index), []).append(entry)

    ranked_items: list[tuple[tuple[int, int, int], SearchCandidate]] = []
    for group in groups.values():
        preferred = next(
            (
                candidate
                for _, provider_name, _, candidate in group
                if provider_name == preferred_provider and candidate.title
            ),
            group[0][3],
        )
        title = preferred.title or group[0][3].title
        aliases: list[str] = []
        year: int | None = None
        scores: dict[str, float] = {}
        identity = AnimeIdentity()

        rank = min(
            (
                0 if provider_name == preferred_provider else 1,
                provider_index,
                item_index,
            )
            for provider_index, provider_name, item_index, _ in group
        )

        for _, _, _, candidate in group:
            aliases.extend([candidate.title, *candidate.aliases])
            if year is None:
                year = candidate.year
            scores.update(candidate.scores)
            identity.merge_missing(candidate.external_ids)

        aliases = [
            value
            for value in _dedupe(aliases)
            if value.casefold() != title.casefold()
        ]
        ranked_items.append(
            (
                rank,
                SearchCandidate(
                    title=title,
                    aliases=aliases,
                    year=year,
                    external_ids=dict(identity.external_ids),
                    scores=scores,
                ),
            )
        )

    ranked_items.sort(
        key=lambda item: (
            item[0],
            -len(item[1].scores),
            item[1].title.casefold(),
        )
    )
    items = [candidate for _, candidate in ranked_items]

    overflow = len(items) > page_size
    return SearchPage(
        items=items[:page_size],
        page=page,
        page_size=page_size,
        has_next=provider_has_next or overflow,
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
