from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from core.identity import AnimeIdentity
from core.models import CharacterRecord


@dataclass(slots=True)
class CharacterLoadResult:
    by_source: dict[str, list[CharacterRecord]] = field(default_factory=dict)
    errors: dict[str, str] = field(default_factory=dict)


class CharacterService:
    """Lazy character loader over the already registered metadata sources."""

    def __init__(self, sources: tuple[Any, ...] | list[Any]) -> None:
        self._sources = tuple(sources)

    async def load(self, identity: AnimeIdentity) -> CharacterLoadResult:
        capable: list[Any] = []
        for source in self._sources:
            source_key = str(getattr(source, "source_key", "") or "").strip().casefold()
            loader = getattr(source, "load_characters", None)
            if source_key and identity.has(source_key) and callable(loader):
                capable.append(source)

        async def run(source: Any):
            try:
                values = await source.load_characters(identity.copy())
                return source.name, list(values or []), None
            except Exception as exc:
                return source.name, [], f"{type(exc).__name__}: {exc}"

        result = CharacterLoadResult()
        if not capable:
            return result

        for source_name, characters, error in await asyncio.gather(*(run(source) for source in capable)):
            if error:
                result.errors[source_name] = error
            elif characters:
                result.by_source[source_name] = characters
        return result
