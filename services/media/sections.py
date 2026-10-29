from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Generic, TypeVar

from core.capabilities import SourceCapability
from core.identity import AnimeIdentity
from core.models import DescriptionDetails, PopularityStats
from sources.runtime.catalog import source_supports

T = TypeVar("T")


@dataclass(slots=True)
class LazySectionLoadResult(Generic[T]):
    by_source: dict[str, T] = field(default_factory=dict)
    key_by_source: dict[str, str] = field(default_factory=dict)
    errors: dict[str, str] = field(default_factory=dict)


class _LazySectionService(Generic[T]):
    loader_name: str
    capability: SourceCapability

    def __init__(self, sources: tuple[Any, ...] | list[Any]) -> None:
        self._sources = tuple(sources)

    async def load(self, identity: AnimeIdentity) -> LazySectionLoadResult[T]:
        capable: list[Any] = []
        for source in self._sources:
            source_key = str(getattr(source, "source_key", "") or "").strip().casefold()
            loader = getattr(source, self.loader_name, None)
            if (
                source_key
                and identity.has(source_key)
                and source_supports(source_key, self.capability)
                and callable(loader)
            ):
                capable.append(source)

        async def run(source: Any):
            source_key = str(getattr(source, "source_key", "") or "").strip().casefold()
            try:
                loader = getattr(source, self.loader_name)
                value = await loader(identity.copy())
                return source.name, source_key, value, None
            except Exception as exc:
                return source.name, source_key, None, f"{type(exc).__name__}: {exc}"

        result: LazySectionLoadResult[T] = LazySectionLoadResult()
        if not capable:
            return result
        for source_name, source_key, value, error in await asyncio.gather(
            *(run(source) for source in capable)
        ):
            result.key_by_source[source_name] = source_key
            if error:
                result.errors[source_name] = error
            elif self._has_data(value):
                result.by_source[source_name] = value
        return result

    def _has_data(self, value: Any) -> bool:
        return value is not None


class ScreenshotService(_LazySectionService[list[str]]):
    loader_name = "load_screenshots"
    capability = SourceCapability.SCREENSHOTS

    def _has_data(self, value: Any) -> bool:
        return bool(value)


class PopularityService(_LazySectionService[PopularityStats]):
    loader_name = "load_popularity"
    capability = SourceCapability.POPULARITY

    def _has_data(self, value: Any) -> bool:
        return isinstance(value, PopularityStats) and value.has_data()


class DescriptionService(_LazySectionService[DescriptionDetails]):
    loader_name = "load_description"
    capability = SourceCapability.DESCRIPTION

    def _has_data(self, value: Any) -> bool:
        return isinstance(value, DescriptionDetails) and value.has_data()
