from __future__ import annotations

from typing import Protocol

from core.models import AnimeRecord, SearchCandidate, SourceSearchPage


class AnimeSource(Protocol):
    """Common contract implemented by every anime data source adapter."""

    name: str

    async def search(
        self,
        query: str,
        *,
        page: int,
        limit: int,
    ) -> SourceSearchPage:
        ...

    async def get_details(self, candidate: SearchCandidate) -> AnimeRecord | None:
        ...
