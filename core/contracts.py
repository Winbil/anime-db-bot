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

    ``source_key`` is the stable key used inside :class:`AnimeIdentity` (for
    example ``mal`` or ``anilist``). Direct-ID search uses this capability rather
    than hard-coding individual databases in Telegram handlers.
    """

    name: str
    source_key: str

    async def get_details(self, identity: AnimeIdentity) -> AnimeRecord | None:
        ...
