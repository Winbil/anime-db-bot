from __future__ import annotations

from typing import Protocol

from core.identity import AnimeIdentity
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
    """Metadata source operating on a source-independent anime identity.

    Sources never perform user-facing text search. Each adapter selects whichever
    external ID it understands from ``AnimeIdentity`` and returns ``None`` when no
    usable ID is known. No database ID is globally mandatory.
    """

    name: str

    async def get_details(self, identity: AnimeIdentity) -> AnimeRecord | None:
        ...
