from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from core.source_keys import SourceKey, normalize_source_key
from core.source_names import MAL_SOURCE_NAME


class SourceCapability(StrEnum):
    SEARCH = "search"
    METADATA = "metadata"
    PEOPLE = "people"
    CHARACTERS = "characters"
    TRAILERS = "trailers"
    EPISODES = "episodes"


@dataclass(frozen=True, slots=True)
class SourceDescriptor:
    key: SourceKey
    display_name: str
    capabilities: frozenset[SourceCapability]
    optional: bool = False

    def supports(self, capability: SourceCapability) -> bool:
        return capability in self.capabilities


SOURCE_CATALOG: tuple[SourceDescriptor, ...] = (
    SourceDescriptor(
        SourceKey.SHIKIMORI,
        "Shikimori",
        frozenset(
            {
                SourceCapability.SEARCH,
                SourceCapability.METADATA,
                SourceCapability.PEOPLE,
                SourceCapability.CHARACTERS,
                SourceCapability.TRAILERS,
            }
        ),
    ),
    SourceDescriptor(
        SourceKey.MAL,
        MAL_SOURCE_NAME,
        frozenset(
            {
                SourceCapability.SEARCH,
                SourceCapability.METADATA,
                SourceCapability.PEOPLE,
                SourceCapability.CHARACTERS,
                SourceCapability.TRAILERS,
                SourceCapability.EPISODES,
            }
        ),
    ),
    SourceDescriptor(
        SourceKey.ANILIST,
        "AniList",
        frozenset(
            {
                SourceCapability.SEARCH,
                SourceCapability.METADATA,
                SourceCapability.PEOPLE,
                SourceCapability.CHARACTERS,
                SourceCapability.TRAILERS,
            }
        ),
    ),
    SourceDescriptor(
        SourceKey.ANIDB,
        "AniDB",
        frozenset(
            {
                SourceCapability.METADATA,
                SourceCapability.PEOPLE,
                SourceCapability.CHARACTERS,
                SourceCapability.EPISODES,
            }
        ),
        optional=True,
    ),
)

SOURCE_DESCRIPTORS: dict[SourceKey, SourceDescriptor] = {
    descriptor.key: descriptor for descriptor in SOURCE_CATALOG
}


def descriptor_for(key: SourceKey | str) -> SourceDescriptor:
    return SOURCE_DESCRIPTORS[normalize_source_key(key)]


def source_supports(key: SourceKey | str, capability: SourceCapability) -> bool:
    return descriptor_for(key).supports(capability)


def source_keys_with(capability: SourceCapability) -> tuple[SourceKey, ...]:
    return tuple(
        descriptor.key
        for descriptor in SOURCE_CATALOG
        if descriptor.supports(capability)
    )


def source_key_for_display_name(display_name: str) -> SourceKey | None:
    normalized = " ".join((display_name or "").split()).strip().casefold()
    for descriptor in SOURCE_CATALOG:
        if descriptor.display_name.casefold() == normalized:
            return descriptor.key
    return None
