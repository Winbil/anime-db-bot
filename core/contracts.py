from __future__ import annotations

from typing import Protocol

from core.identity import AnimeIdentity
from core.models import AnimeRecord, EpisodePage, EpisodeRecord, SearchPage, TrailerRecord


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


class AnimeEpisodeSource(Protocol):
    """Lazy episode capability supplied by one backend.

    A backend may reuse another database identity edge. Jikan, for example,
    advertises ``source_key='mal'`` and ``backend_key='jikan'`` instead of
    introducing a synthetic Jikan identity.
    """

    name: str
    display_name: str
    source_key: str
    backend_key: str

    async def load_episode_page(
        self,
        identity: AnimeIdentity,
        *,
        page: int = 1,
    ) -> EpisodePage:
        ...

    async def load_episode(
        self,
        identity: AnimeIdentity,
        episode_number: int,
    ) -> EpisodeRecord | None:
        ...


class AnimeTrailerSource(Protocol):
    """Lazy promotional-video capability supplied by one backend."""

    name: str
    display_name: str
    source_key: str
    backend_key: str

    async def load_trailers(self, identity: AnimeIdentity) -> list[TrailerRecord]:
        ...
