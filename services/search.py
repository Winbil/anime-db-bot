from __future__ import annotations

import asyncio
import re
import time
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher

from core.canonicalization import contains_cyrillic, normalize_key, transliterate_ru
from core.contracts import AnimeSearchProvider
from core.identity import AnimeIdentity
from core.models import SearchCandidate, SearchPage, SearchResultSet
from core.settings import AppSettings, SearchSettings


_LOW_SIGNAL_TOKENS = frozenset({
    "the",
    "and",
    "for",
    "with",
    "from",
    "into",
    "that",
    "this",
    "как",
    "что",
    "это",
    "для",
    "при",
    "под",
    "над",
    "без",
    "про",
    "kak",
    "chto",
    "eto",
    "dlya",
    "pri",
    "pod",
    "nad",
    "bez",
    "pro",
})


@dataclass(slots=True)
class _CacheEntry:
    expires_at: float
    page: SearchPage


@dataclass(slots=True)
class _ResultSetCacheEntry:
    expires_at: float
    result_set: SearchResultSet


@dataclass(slots=True)
class _CandidateGroup:
    identity: AnimeIdentity
    entries: list[tuple[int, str, int, SearchCandidate]]


class SearchService:
    """Search providers, filter relevance and merge source-independent results.

    ``search()`` remains the low-level page API used by compatibility code and
    tests. New interactive UI should use ``collect()``: it forms one query-scoped
    relevant result set first, then Telegram paginates that frozen merged list
    locally instead of fetching progressively less relevant upstream pages.
    """

    def __init__(
        self,
        providers: tuple[AnimeSearchProvider, ...] | list[AnimeSearchProvider],
        *,
        settings: SearchSettings | None = None,
    ) -> None:
        self._providers = tuple(providers)
        if not self._providers:
            raise ValueError("SearchService requires at least one search provider")
        self._settings = settings or AppSettings.from_env().search
        self._cache: dict[tuple[str, int, int], _CacheEntry] = {}
        self._result_set_cache: dict[tuple[str, int, int, int, int], _ResultSetCacheEntry] = {}

    @property
    def provider_names(self) -> tuple[str, ...]:
        return tuple(provider.name for provider in self._providers)

    @property
    def provider_name(self) -> str:
        return ", ".join(self.provider_names)

    @property
    def settings(self) -> SearchSettings:
        return self._settings

    def _cache_ttl(self) -> int:
        return max(0, int(self._settings.cache_ttl_seconds))

    def _cache_max_entries(self) -> int:
        return max(10, int(self._settings.cache_max_entries))

    def _collection_page_size(self) -> int:
        return min(max(5, int(self._settings.collection_page_size)), 50)

    def _collection_max_pages(self) -> int:
        return min(max(1, int(self._settings.collection_max_pages)), 20)

    def _relevance_threshold(self) -> int:
        return min(max(1, int(self._settings.relevance_threshold)), 100)

    def _irrelevant_tail_pages(self) -> int:
        return min(max(1, int(self._settings.irrelevant_tail_pages)), 5)

    def _collection_max_items(self) -> int:
        return min(max(10, int(self._settings.collection_max_items)), 1000)

    async def search(
        self,
        query: str,
        *,
        page: int = 1,
        page_size: int = 10,
    ) -> SearchPage:
        """Fetch and merge one upstream page from every configured provider."""
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
            _trim_cache(self._cache, self._cache_max_entries())

        return merged

    async def collect(
        self,
        query: str,
        *,
        page_size: int | None = None,
        max_pages: int | None = None,
    ) -> SearchResultSet:
        """Collect a stable relevant result set for one textual query.

        Providers are paged independently. A full provider page with no candidate
        reaching the relevance threshold counts as an irrelevant-tail page. Once
        the configured tail streak is reached, further upstream pages are not
        fetched. If the hard page/item safety cap is reached while relevant data
        may still exist, ``complete`` is false so UI can render a ``+`` count.
        """
        query = _normalize_query(query)
        if not query:
            return SearchResultSet(items=[])

        page_size = max(1, int(page_size or self._collection_page_size()))
        max_pages = max(1, int(max_pages or self._collection_max_pages()))
        threshold = self._relevance_threshold()
        tail_pages = self._irrelevant_tail_pages()
        max_items = self._collection_max_items()
        cache_key = (query.casefold(), page_size, max_pages, threshold, tail_pages)

        cached = self._result_set_cache.get(cache_key)
        now = time.monotonic()
        if cached is not None and cached.expires_at > now:
            self._result_set_cache.pop(cache_key, None)
            self._result_set_cache[cache_key] = cached
            return cached.result_set
        if cached is not None:
            self._result_set_cache.pop(cache_key, None)

        async def collect_provider(
            provider_index: int,
            provider: AnimeSearchProvider,
        ) -> tuple[list[tuple[int, str, int, SearchCandidate]], str | None, bool]:
            entries: list[tuple[int, str, int, SearchCandidate]] = []
            irrelevant_streak = 0
            complete = True

            for page_number in range(1, max_pages + 1):
                try:
                    page = await provider.search(
                        query,
                        page=page_number,
                        limit=page_size,
                    )
                except Exception as exc:
                    return (
                        entries,
                        f"{type(exc).__name__}: {exc}",
                        False,
                    )

                relevant_count = 0
                for item_index, candidate in enumerate(page.items):
                    if _relevance_score(query, candidate) < threshold:
                        continue
                    relevant_count += 1
                    provider_rank = (page_number - 1) * page_size + item_index
                    entries.append(
                        (provider_index, provider.name, provider_rank, candidate)
                    )

                if relevant_count:
                    irrelevant_streak = 0
                else:
                    irrelevant_streak += 1

                if not page.has_next:
                    break
                if irrelevant_streak >= tail_pages:
                    # Search APIs are relevance ordered. One or more complete
                    # pages below threshold define the query's irrelevant tail.
                    break
                if page_number >= max_pages:
                    complete = False
                    break

            return entries, None, complete

        provider_results = await asyncio.gather(
            *(
                collect_provider(provider_index, provider)
                for provider_index, provider in enumerate(self._providers)
            )
        )

        entries: list[tuple[int, str, int, SearchCandidate]] = []
        errors: dict[str, str] = {}
        complete = True
        for provider, (provider_entries, error, provider_complete) in zip(
            self._providers,
            provider_results,
            strict=True,
        ):
            entries.extend(provider_entries)
            complete = complete and provider_complete
            if error:
                errors[provider.name] = error

        items = _merge_entries(query, entries, allow_title_merge=True)
        items.sort(key=lambda candidate: -_relevance_score(query, candidate))
        if len(items) > max_items:
            items = items[:max_items]
            complete = False

        result_set = SearchResultSet(
            items=items,
            complete=complete and not errors,
            errors=errors,
        )

        ttl = self._cache_ttl()
        if ttl > 0 and not errors:
            self._result_set_cache[cache_key] = _ResultSetCacheEntry(
                expires_at=time.monotonic() + ttl,
                result_set=result_set,
            )
            _trim_cache(self._result_set_cache, self._cache_max_entries())

        return result_set


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
    """Layer 2: merge unresolved groups by exact normalized romaji title."""
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


def _merge_entries(
    query: str,
    entries: list[tuple[int, str, int, SearchCandidate]],
    *,
    allow_title_merge: bool,
) -> list[SearchCandidate]:
    identity_groups = _group_entries_by_identity(entries)
    groups = (
        _merge_groups_by_romaji(identity_groups)
        if allow_title_merge
        else identity_groups
    )

    use_russian_title = bool(re.search(r"[а-яё]", query, flags=re.IGNORECASE))
    preferred_provider = "Shikimori" if use_russian_title else "MyAnimeList"
    ranked_items: list[tuple[tuple[int, int, int], SearchCandidate]] = []

    for candidate_group in groups:
        group = sorted(candidate_group.entries, key=lambda entry: (entry[0], entry[2]))
        if not group:
            continue

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
        posters: list[str] = []
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
            posters.extend(candidate.posters)
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
                    posters=_dedupe(posters),
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
    return [candidate for _, candidate in ranked_items]


def merge_candidates(
    candidates: list[SearchCandidate],
    *,
    query: str = "",
    allow_title_merge: bool = True,
) -> list[SearchCandidate]:
    """Merge an already collected list using the same conflict-safe identity logic."""
    entries = [
        (index, f"candidate:{index}", 0, candidate)
        for index, candidate in enumerate(candidates)
    ]
    return _merge_entries(query, entries, allow_title_merge=allow_title_merge)


def _merge_results(
    query: str,
    results: list[tuple[str, SearchPage | None, str | None]],
    *,
    page: int,
    page_size: int,
) -> SearchPage:
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

    items = _merge_entries(query, entries, allow_title_merge=True)
    overflow = len(items) > page_size
    return SearchPage(
        items=items[:page_size],
        page=page,
        page_size=page_size,
        has_next=provider_has_next or overflow,
        errors=errors,
    )


def _candidate_texts(candidate: SearchCandidate) -> list[str]:
    return _dedupe([
        candidate.title,
        candidate.romaji_title or "",
        *candidate.aliases,
    ])


def _unicode_search_key(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value or "").casefold()
    characters: list[str] = []
    for character in normalized:
        category = unicodedata.category(character)
        if character.isalnum() or category.startswith("L") or category.startswith("N"):
            characters.append(character)
        else:
            characters.append(" ")
    return " ".join("".join(characters).split())


def _normalized_variants(value: str) -> set[str]:
    variants: set[str] = set()
    normalized = normalize_key(value)
    if normalized:
        variants.add(normalized)

    # normalize_key intentionally targets Latin/Cyrillic canonical values. The
    # search relevance layer must additionally preserve native scripts (Japanese,
    # Korean, Chinese, etc.) so exact/native-title queries are not filtered out.
    unicode_key = _unicode_search_key(value)
    if unicode_key:
        variants.add(unicode_key)

    if contains_cyrillic(value):
        transliterated = normalize_key(transliterate_ru(value))
        if transliterated:
            variants.add(transliterated)
    return variants


def _meaningful_tokens(value: str) -> set[str]:
    tokens = set(value.split())
    meaningful = {
        token
        for token in tokens
        if len(token) >= 3 and token not in _LOW_SIGNAL_TOKENS
    }
    # A short one-token title such as "86" must remain searchable. Only discard
    # low-signal words when the query also contains something more informative.
    return meaningful or tokens


def _relevance_score(query: str, candidate: SearchCandidate) -> int:
    """Return a conservative source-independent title relevance score (0..100)."""
    query_variants = _normalized_variants(query)
    if not query_variants:
        return 0

    candidate_variants: set[str] = set()
    for value in _candidate_texts(candidate):
        candidate_variants.update(_normalized_variants(value))
    if not candidate_variants:
        return 0

    best = 0.0
    for query_key in query_variants:
        query_tokens = _meaningful_tokens(query_key)
        for candidate_key in candidate_variants:
            candidate_tokens = _meaningful_tokens(candidate_key)
            if query_key == candidate_key:
                return 100
            if candidate_key.startswith(query_key) or query_key.startswith(candidate_key):
                best = max(best, 94.0)
            if query_tokens and query_tokens <= candidate_tokens:
                best = max(best, 90.0)
            if len(query_key) >= 3 and query_key in candidate_key:
                best = max(best, 86.0)

            matched_tokens = len(query_tokens & candidate_tokens)
            overlap = matched_tokens / len(query_tokens) if query_tokens else 0.0
            ratio = SequenceMatcher(None, query_key, candidate_key).ratio()
            minimum_matches = 1 if len(query_tokens) <= 1 else 2
            if matched_tokens >= minimum_matches and overlap >= 0.5:
                best = max(best, 48.0 + overlap * 34.0 + ratio * 8.0)
            elif ratio >= 0.84:
                best = max(best, 35.0 + ratio * 45.0)

    return max(0, min(100, round(best)))


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


def _trim_cache(cache: dict, maximum: int) -> None:
    while len(cache) > maximum:
        cache.pop(next(iter(cache)), None)
