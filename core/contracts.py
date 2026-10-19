from __future__ import annotations

from typing import Protocol

from core.models import AnimeRecord, SearchCandidate, SourceSearchPage


class AnimeSource(Protocol):
    """Source adapter contract known by services, but independent of implementations."""

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
