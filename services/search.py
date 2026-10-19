from __future__ import annotations

import asyncio
import re

from core.contracts import AnimeSource
from core.models import SearchCandidate, SearchPage, SourceSearchHit


def _dedupe_strings(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        value = (value or "").strip()
        key = value.casefold()
        if value and key not in seen:
            seen.add(key)
            result.append(value)
    return result


def _normalize_title(value: str) -> str:
    return re.sub(r"[^a-z0-9а-яё]+", "", value.casefold())


def _candidate_key(hit: SourceSearchHit) -> tuple[str, str | int | None]:
    mal_id = hit.external_ids.get("mal")
    if mal_id:
        return ("id:mal", mal_id)
    return (_normalize_title(hit.title), hit.year)


class SearchService:
    """Search all configured sources without knowing concrete implementations."""

    def __init__(self, sources: tuple[AnimeSource, ...] | list[AnimeSource]) -> None:
        self._sources = tuple(sources)

    async def search(
        self,
        query: str,
        *,
        page: int = 1,
        page_size: int = 10,
    ) -> SearchPage:
        page = max(1, int(page))
        page_size = max(1, int(page_size))

        async def run(source: AnimeSource):
            try:
                result = await source.search(query, page=page, limit=page_size)
                return source.name, result, None
            except Exception as exc:
                return source.name, None, f"{type(exc).__name__}: {exc}"

        raw_results = await asyncio.gather(*(run(source) for source in self._sources))

        merged: dict[tuple[str, str | int | None], SearchCandidate] = {}
        errors: dict[str, str] = {}
        has_next = False

        for source_name, source_page, error in raw_results:
            if error:
                errors[source_name] = error
                continue
            if source_page is None:
                continue

            has_next = has_next or source_page.has_next
            for hit in source_page.items:
                key = _candidate_key(hit)
                candidate = merged.get(key)
                if candidate is None:
                    candidate = SearchCandidate(
                        title=hit.title,
                        aliases=_dedupe_strings(hit.aliases),
                        year=hit.year,
                        source_refs={hit.source: hit.source_id},
                        external_ids=dict(hit.external_ids),
                        scores={hit.source: hit.score} if hit.score is not None else {},
                    )
                    merged[key] = candidate
                    continue

                candidate.aliases = _dedupe_strings(
                    [*candidate.aliases, hit.title, *hit.aliases]
                )
                candidate.source_refs[hit.source] = hit.source_id
                candidate.external_ids.update(
                    {id_name: value for id_name, value in hit.external_ids.items() if value}
                )
                if hit.score is not None:
                    candidate.scores[hit.source] = hit.score
                if candidate.year is None:
                    candidate.year = hit.year

        items = list(merged.values())
        items.sort(
            key=lambda item: (
                max(item.scores.values(), default=0.0),
                len(item.source_refs),
            ),
            reverse=True,
        )

        return SearchPage(
            items=items,
            page=page,
            page_size=page_size,
            has_next=has_next,
            errors=errors,
        )
