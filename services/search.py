from __future__ import annotations

import asyncio
import os
import re
import time
from dataclasses import dataclass

from core.canonicalization import normalize_key
from core.contracts import AnimeSearchProvider
from core.identity import AnimeIdentity
from core.models import SearchCandidate, SearchPage


@dataclass(slots=True)
class _CacheEntry:
    expires_at: float
    page: SearchPage


@dataclass(slots=True)
class _CandidateGroup:
    identity: AnimeIdentity
    entries: list[tuple[int, str, int, SearchCandidate]]


class SearchService:
    """Search providers and merge candidates through layered identity matching.

    Layer 1 uses confirmed shared external IDs. Layer 2 is a conservative
    fallback for databases without cross-ID mappings and matches exact normalized
    romaji titles while respecting source-ID conflicts and known release years.
    """

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


def _group_entries_by_identity(
    entries: list[tuple[int, str, int, SearchCandidate]],
) -> list[_CandidateGroup]:
    """Layer 1: build conflict-safe clusters from confirmed external IDs."""
    groups: list[_CandidateGroup] = []

    for entry in entries:
        candidate_identity = entry[3].identity
        if candidate_identity.is_empty():
            groups.append(_CandidateGroup(candidate_identity, [entry]))
            continue

        matching_indexes = [
            index
            for index, group in enumerate(groups)
            if not group.identity.is_empty() and group.identity.matches(candidate_identity)
        ]
        if not matching_indexes:
            groups.append(_CandidateGroup(candidate_identity.copy(), [entry]))
            continue

        combined = candidate_identity.copy()
        ambiguous = False
        for index in matching_indexes:
            group_identity = groups[index].identity
            if combined.conflicting_ids(group_identity):
                ambiguous = True
                break
            combined.merge_missing(group_identity)

        if ambiguous:
            groups.append(_CandidateGroup(candidate_identity.copy(), [entry]))
            continue

        target_index = matching_indexes[0]
        target_entries = [entry]
        for index in matching_indexes:
            target_entries.extend(groups[index].entries)

        for index in reversed(matching_indexes):
            groups.pop(index)

        insertion_index = min(target_index, len(groups))
        groups.insert(
            insertion_index,
            _CandidateGroup(combined, target_entries),
        )

    return groups


def _romaji_keys(group: _CandidateGroup) -> set[str]:
    result: set[str] = set()
    for _, _, _, candidate in group.entries:
        value = normalize_key(candidate.romaji_title or "")
        if value:
            result.add(value)
    return result


def _years(group: _CandidateGroup) -> set[int]:
    return {
        candidate.year
        for _, _, _, candidate in group.entries
        if isinstance(candidate.year, int) and not isinstance(candidate.year, bool)
    }


def _years_compatible(left: set[int], right: set[int]) -> bool:
    return not left or not right or bool(left & right)


def _merge_groups_by_romaji(groups: list[_CandidateGroup]) -> list[_CandidateGroup]:
    """Layer 2: merge unresolved groups by exact normalized romaji title.

    This fallback deliberately does not use fuzzy similarity. It also refuses to
    join groups when they contain conflicting IDs for the same database or when
    both sides have known, non-overlapping release years.
    """
    merged: list[_CandidateGroup] = []

    for group in groups:
        keys = _romaji_keys(group)
        if not keys:
            merged.append(group)
            continue

        group_years = _years(group)
        matching_indexes = [
            index
            for index, existing in enumerate(merged)
            if keys & _romaji_keys(existing)
            and not group.identity.conflicting_ids(existing.identity)
            and _years_compatible(group_years, _years(existing))
        ]
        if not matching_indexes:
            merged.append(group)
            continue

        combined_identity = group.identity.copy()
        combined_entries = list(group.entries)
        combined_years = set(group_years)
        ambiguous = False

        for index in matching_indexes:
            existing = merged[index]
            if combined_identity.conflicting_ids(existing.identity):
                ambiguous = True
                break
            if not _years_compatible(combined_years, _years(existing)):
                ambiguous = True
                break
            combined_identity.merge_missing(existing.identity)
            combined_entries.extend(existing.entries)
            combined_years.update(_years(existing))

        if ambiguous:
            merged.append(group)
            continue

        target_index = matching_indexes[0]
        for index in reversed(matching_indexes):
            merged.pop(index)

        insertion_index = min(target_index, len(merged))
        merged.insert(
            insertion_index,
            _CandidateGroup(combined_identity, combined_entries),
        )

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

    identity_groups = _group_entries_by_identity(entries)
    groups = _merge_groups_by_romaji(identity_groups)
    ranked_items: list[tuple[tuple[int, int, int], SearchCandidate]] = []

    for candidate_group in groups:
        group = sorted(
            candidate_group.entries,
            key=lambda entry: (entry[0], entry[2]),
        )
        preferred = next(
            (
                candidate
                for _, provider_name, _, candidate in group
                if provider_name == preferred_provider and candidate.title
            ),
            group[0][3],
        )
        title = preferred.title or group[0][3].title
        romaji_title = preferred.romaji_title or next(
            (
                candidate.romaji_title
                for _, _, _, candidate in group
                if candidate.romaji_title
            ),
            None,
        )
        aliases: list[str] = []
        year: int | None = None
        scores: dict[str, float] = {}

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
                    external_ids=dict(candidate_group.identity.external_ids),
                    scores=scores,
                    romaji_title=romaji_title,
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
