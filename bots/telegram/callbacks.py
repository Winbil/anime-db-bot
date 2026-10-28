from __future__ import annotations

from dataclasses import dataclass

MAX_CALLBACK_BYTES = 64


def _encode(parts: list[str]) -> str:
    value = ":".join(parts)
    if len(value.encode("utf-8")) > MAX_CALLBACK_BYTES:
        raise ValueError("Telegram callback_data exceeds 64 bytes")
    if any(":" in part for part in parts):
        raise ValueError("Callback fields must not contain ':'")
    return value


def _non_negative(value: str) -> int | None:
    if not value.isdigit():
        return None
    return int(value)


@dataclass(frozen=True, slots=True)
class ViewCallback:
    token: str
    section: str
    page: int = 0

    prefix = "av"

    def encode(self) -> str:
        return _encode([self.prefix, self.token, self.section, str(max(0, int(self.page)))])

    @classmethod
    def parse(cls, raw: str | None) -> "ViewCallback | None":
        parts = (raw or "").split(":")
        if len(parts) != 4 or parts[0] != cls.prefix:
            return None
        page = _non_negative(parts[3])
        if page is None or not parts[1] or not parts[2]:
            return None
        return cls(parts[1], parts[2], page)


@dataclass(frozen=True, slots=True)
class SectionSourceCallback:
    token: str
    section: str
    source_index: int
    page: int = 0

    prefix = "as"

    def encode(self) -> str:
        return _encode([
            self.prefix,
            self.token,
            self.section,
            str(max(0, int(self.source_index))),
            str(max(0, int(self.page))),
        ])

    @classmethod
    def parse(cls, raw: str | None) -> "SectionSourceCallback | None":
        parts = (raw or "").split(":")
        if len(parts) != 5 or parts[0] != cls.prefix:
            return None
        source_index = _non_negative(parts[3])
        page = _non_negative(parts[4])
        if source_index is None or page is None or not parts[1] or not parts[2]:
            return None
        return cls(parts[1], parts[2], source_index, page)


@dataclass(frozen=True, slots=True)
class IndexedCallback:
    prefix: str
    token: str
    index: int
    page: int = 0

    def encode(self) -> str:
        return _encode([
            self.prefix,
            self.token,
            str(max(0, int(self.index))),
            str(max(0, int(self.page))),
        ])

    @classmethod
    def parse(cls, raw: str | None, *, prefix: str) -> "IndexedCallback | None":
        parts = (raw or "").split(":")
        if len(parts) != 4 or parts[0] != prefix:
            return None
        index = _non_negative(parts[2])
        page = _non_negative(parts[3])
        if index is None or page is None or not parts[1]:
            return None
        return cls(prefix, parts[1], index, page)


@dataclass(frozen=True, slots=True)
class EpisodeDetailCallback:
    token: str
    backend_index: int
    episode_number: int
    return_page: int

    prefix = "ae"

    def encode(self) -> str:
        return _encode([
            self.prefix,
            self.token,
            str(max(0, int(self.backend_index))),
            str(max(1, int(self.episode_number))),
            str(max(0, int(self.return_page))),
        ])

    @classmethod
    def parse(cls, raw: str | None) -> "EpisodeDetailCallback | None":
        parts = (raw or "").split(":")
        if len(parts) == 4 and parts[0] == cls.prefix:
            episode = _non_negative(parts[2])
            page = _non_negative(parts[3])
            if episode is None or episode <= 0 or page is None or not parts[1]:
                return None
            return cls(parts[1], 0, episode, page)
        if len(parts) != 5 or parts[0] != cls.prefix:
            return None
        backend = _non_negative(parts[2])
        episode = _non_negative(parts[3])
        page = _non_negative(parts[4])
        if (
            backend is None
            or episode is None
            or episode <= 0
            or page is None
            or not parts[1]
        ):
            return None
        return cls(parts[1], backend, episode, page)
