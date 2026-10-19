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
    """Metadata source. Sources receive a MAL ID and do not implement text search."""

    name: str

    async def get_details(self, mal_id: str) -> AnimeRecord | None:
        ...
