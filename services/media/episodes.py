from __future__ import annotations

from core.contracts import AnimeEpisodeSource
from core.identity import AnimeIdentity
from core.models import EpisodePage, EpisodeRecord


class EpisodeService:
    """Source-independent entry point for lazy episode capabilities."""

    def __init__(
        self, sources: tuple[AnimeEpisodeSource, ...] | list[AnimeEpisodeSource]
    ) -> None:
        self._sources = tuple(sources)
        self._by_backend = {source.backend_key: source for source in self._sources}

    @property
    def sources(self) -> tuple[AnimeEpisodeSource, ...]:
        return self._sources

    @staticmethod
    def _supports_identity(source: AnimeEpisodeSource, identity: AnimeIdentity) -> bool:
        checker = getattr(source, "supports_identity", None)
        if callable(checker):
            return bool(checker(identity))
        return bool(source.source_key and identity.has(source.source_key))

    def display_name(self, backend: str = "jikan") -> str:
        source = self._by_backend.get(backend)
        return source.display_name if source is not None else backend

    def available_backends(self, identity: AnimeIdentity) -> list[str]:
        return [
            source.backend_key
            for source in self._sources
            if self._supports_identity(source, identity)
        ]

    async def load_page(
        self,
        identity: AnimeIdentity,
        *,
        page: int = 1,
        backend: str = "jikan",
    ) -> EpisodePage:
        source = self._by_backend.get(backend)
        if source is None:
            raise ValueError(f"Unknown episode backend: {backend}")
        if not self._supports_identity(source, identity):
            return EpisodePage(items=[], page=max(1, int(page)), has_next=False)
        return await source.load_episode_page(identity, page=page)

    async def load_catalog(
        self,
        identity: AnimeIdentity,
        *,
        backend: str = "jikan",
        first_page: EpisodePage | None = None,
    ) -> list[EpisodeRecord]:
        """Return a complete episode catalog only when it is already cheap to know.

        Providers may expose a dedicated ``load_episode_catalog`` capability.  For
        ordinary paginated sources we reuse a fully loaded first page, but never
        crawl additional upstream pages merely to discover seasons.
        """
        source = self._by_backend.get(backend)
        if source is None:
            raise ValueError(f"Unknown episode backend: {backend}")
        if not self._supports_identity(source, identity):
            return []

        loader = getattr(source, "load_episode_catalog", None)
        if callable(loader):
            return list(await loader(identity))
        if first_page is not None and first_page.page == 1 and not first_page.has_next:
            return list(first_page.items)
        return []

    async def load_episode(
        self,
        identity: AnimeIdentity,
        episode_number: int,
        *,
        backend: str = "jikan",
    ) -> EpisodeRecord | None:
        source = self._by_backend.get(backend)
        if source is None:
            raise ValueError(f"Unknown episode backend: {backend}")
        if not self._supports_identity(source, identity):
            return None
        return await source.load_episode(identity, episode_number)
