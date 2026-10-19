from __future__ import annotations

from core.contracts import AnimeSearchProvider
from core.models import SearchPage


class SearchService:
    """Search through one dedicated search provider, independent from metadata sources."""

    def __init__(self, provider: AnimeSearchProvider) -> None:
        self._provider = provider

    @property
    def provider_name(self) -> str:
        return self._provider.name

    async def search(
        self,
        query: str,
        *,
        page: int = 1,
        page_size: int = 10,
    ) -> SearchPage:
        return await self._provider.search(
            query,
            page=max(1, int(page)),
            limit=max(1, int(page_size)),
        )
