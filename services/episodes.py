from __future__ import annotations

from core.contracts import AnimeEpisodeSource
from core.identity import AnimeIdentity
from core.models import EpisodePage, EpisodeRecord


class EpisodeService:
    """Source-independent entry point for lazy episode capabilities."""

    def __init__(self, sources: tuple[AnimeEpisodeSource, ...] | list[AnimeEpisodeSource]) -> None:
        self._sources = tuple(sources)
        self._by_backend = {source.backend_key: source for source in self._sources}

    @property
    def sources(self) -> tuple[AnimeEpisodeSource, ...]:
        return self._sources

    def display_name(self, backend: str = "jikan") -> str:
        source = self._by_backend.get(backend)
        return source.display_name if source is not None else backend

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
        return await source.load_episode_page(identity, page=page)

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
        return await source.load_episode(identity, episode_number)
