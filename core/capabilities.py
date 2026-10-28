from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from core.source_keys import SourceKey


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
