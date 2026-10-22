from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping


def _normalize_source(value: object) -> str:
    return str(value or "").strip().casefold()


def _normalize_id(value: object) -> str:
    return str(value or "").strip()


@dataclass(slots=True)
class AnimeIdentity:
    """Source-independent identity graph for one anime.

    There is deliberately no primary database ID. Every known external identifier
    is a peer edge in the identity graph, for example ``mal:123``,
    ``anilist:456`` or ``shikimori:789``. New integrations only need to add their
    own stable source key and ID.
    """

    external_ids: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.external_ids = self._normalized(self.external_ids)

    @staticmethod
    def _normalized(values: Mapping[str, object] | None) -> dict[str, str]:
        result: dict[str, str] = {}
        for raw_source, raw_id in (values or {}).items():
            source = _normalize_source(raw_source)
            external_id = _normalize_id(raw_id)
            if source and external_id:
                result[source] = external_id
        return result

    @classmethod
    def from_mapping(cls, values: Mapping[str, object] | None) -> "AnimeIdentity":
        return cls(dict(values or {}))

    def copy(self) -> "AnimeIdentity":
        return AnimeIdentity(dict(self.external_ids))

    def get(self, source: str) -> str | None:
        return self.external_ids.get(_normalize_source(source))

    def has(self, source: str) -> bool:
        return bool(self.get(source))

    def is_empty(self) -> bool:
        return not self.external_ids

    def shared_ids(self, other: "AnimeIdentity") -> dict[str, str]:
        return {
            source: value
            for source, value in self.external_ids.items()
            if other.external_ids.get(source) == value
        }

    def conflicting_ids(self, other: "AnimeIdentity") -> dict[str, tuple[str, str]]:
        result: dict[str, tuple[str, str]] = {}
        for source in set(self.external_ids) & set(other.external_ids):
            left = self.external_ids[source]
            right = other.external_ids[source]
            if left != right:
                result[source] = (left, right)
        return result

    def matches(self, other: "AnimeIdentity") -> bool:
        """Return true only for a confirmed non-conflicting identity overlap."""
        return bool(self.shared_ids(other)) and not self.conflicting_ids(other)

    def merge_missing(self, values: Mapping[str, object] | "AnimeIdentity") -> dict[str, tuple[str, str]]:
        """Add previously unknown IDs without overwriting conflicting evidence.

        Returns any conflicts found so callers can log or surface inconsistent
        upstream mappings while keeping the already-known identity stable.
        """
        incoming = (
            values.external_ids
            if isinstance(values, AnimeIdentity)
            else self._normalized(values)
        )
        conflicts: dict[str, tuple[str, str]] = {}
        for source, external_id in incoming.items():
            current = self.external_ids.get(source)
            if current is None:
                self.external_ids[source] = external_id
            elif current != external_id:
                conflicts[source] = (current, external_id)
        return conflicts

    def fingerprint(self) -> tuple[tuple[str, str], ...]:
        """Deterministic runtime fingerprint, not a persistent primary key."""
        return tuple(sorted(self.external_ids.items()))

    def describe(self) -> str:
        if not self.external_ids:
            return "no external IDs"
        return ", ".join(
            f"{source}:{external_id}"
            for source, external_id in sorted(self.external_ids.items())
        )
