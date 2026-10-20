from __future__ import annotations

from typing import Protocol

from core.models import AnimeRecord, SearchPage


class AnimeSearchProvider(Protocol):
    """Dedicated anime search backend, independent from metadata sources."""

    name: str

    async def search(
        self,
        query: str,
        *,
        page: int,
        limit: int,
    ) -> SearchPage:
        ...


class AnimeSource(Protocol):
    """Metadata source.

    Sources never perform text search. They receive the selected MAL ID plus any
    cross-database IDs that search providers already discovered.
    """

    name: str

    async def get_details(
        self,
        mal_id: str,
        known_ids: dict[str, str],
    ) -> AnimeRecord | None:
        ...
