from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from core.contracts import AnimeTrailerSource
from core.identity import AnimeIdentity
from core.models import TrailerRecord


@dataclass(slots=True)
class TrailerLoadResult:
    by_source: dict[str, list[TrailerRecord]] = field(default_factory=dict)
    errors: dict[str, str] = field(default_factory=dict)


class TrailerService:
    """Load promotional trailers lazily from every applicable backend."""

    def __init__(self, sources: tuple[AnimeTrailerSource, ...] | list[AnimeTrailerSource]) -> None:
        self._sources = tuple(sources)

    @property
    def sources(self) -> tuple[AnimeTrailerSource, ...]:
        return self._sources

    async def load(self, identity: AnimeIdentity) -> TrailerLoadResult:
        applicable = [
            source
            for source in self._sources
            if identity.has(str(source.source_key).casefold())
        ]

        async def run(source: AnimeTrailerSource):
            try:
                items = await source.load_trailers(identity.copy())
                return source.display_name, list(items), None
            except Exception as exc:
                return source.display_name, [], f"{type(exc).__name__}: {exc}"

        if not applicable:
            return TrailerLoadResult()

        result = TrailerLoadResult()
        for source_name, items, error in await asyncio.gather(*(run(source) for source in applicable)):
            if error:
                result.errors[source_name] = error
            if items:
                result.by_source[source_name] = items
        return result
