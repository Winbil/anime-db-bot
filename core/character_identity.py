from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping


def _clean_provider(value: object) -> str:
    return str(value or "").strip().casefold()


def _clean_id(value: object) -> str:
    return str(value or "").strip()


@dataclass(slots=True)
class CharacterIdentity:
    """Conflict-safe source-local identity for one character.

    Character IDs belong to their own namespace and are never mixed with anime
    or person IDs. A shared provider ID confirms a match; different IDs from the
    same provider are a hard conflict. Name equality is only a presentation
    fallback and never canonical identity evidence.
    """

    external_ids: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.external_ids = self._normalize(self.external_ids)

    @classmethod
    def from_mapping(cls, values: Mapping[str, object] | None) -> "CharacterIdentity":
        return cls(dict(values or {}))

    @staticmethod
    def _normalize(values: Mapping[str, object]) -> dict[str, str]:
        result: dict[str, str] = {}
        for raw_provider, raw_id in values.items():
            provider = _clean_provider(raw_provider)
            external_id = _clean_id(raw_id)
            if provider and external_id:
                result[provider] = external_id
        return result

    def conflicts_with(self, other: "CharacterIdentity") -> bool:
        shared = set(self.external_ids) & set(other.external_ids)
        return any(self.external_ids[key] != other.external_ids[key] for key in shared)

    def matches(self, other: "CharacterIdentity") -> bool:
        shared = set(self.external_ids) & set(other.external_ids)
        return bool(shared) and not self.conflicts_with(other)

    def merge_missing(self, values: "CharacterIdentity | Mapping[str, object]") -> None:
        incoming = (
            values.external_ids
            if isinstance(values, CharacterIdentity)
            else self._normalize(values)
        )
        for provider, external_id in incoming.items():
            existing = self.external_ids.get(provider)
            if existing is None:
                self.external_ids[provider] = external_id
            elif existing != external_id:
                continue
