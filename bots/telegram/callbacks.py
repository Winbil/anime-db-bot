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


def resolve_key_or_legacy_index(selector: str | None, keys: list[str]) -> str:
    """Resolve a stable callback key, accepting old numeric list indices."""
    if not keys:
        raise ValueError("No callback keys are available")
    if selector is None or selector == "":
        return keys[0]
    if selector in keys:
        return selector
    if selector.isdigit():
        index = int(selector)
        if 0 <= index < len(keys):
            return keys[index]
    raise ValueError(f"Callback key is unavailable: {selector}")


@dataclass(frozen=True, slots=True)
class ViewCallback:
    token: str
    section: str
    page: int = 0

    prefix = "av"

    def encode(self) -> str:
        return _encode(
            [self.prefix, self.token, self.section, str(max(0, int(self.page)))]
        )

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
    source_key: str
    page: int = 0

    prefix = "as"

    def encode(self) -> str:
        if not self.source_key:
            raise ValueError("Source key must not be empty")
        return _encode(
            [
                self.prefix,
                self.token,
                self.section,
                self.source_key,
                str(max(0, int(self.page))),
            ]
        )

    @classmethod
    def parse(cls, raw: str | None) -> "SectionSourceCallback | None":
        parts = (raw or "").split(":")
        if len(parts) != 5 or parts[0] != cls.prefix:
            return None
        page = _non_negative(parts[4])
        if page is None or not parts[1] or not parts[2] or not parts[3]:
            return None
        return cls(parts[1], parts[2], parts[3], page)


@dataclass(frozen=True, slots=True)
class KeyedPageCallback:
    prefix: str
    token: str
    key: str
    page: int = 0

    def encode(self) -> str:
        if not self.key:
            raise ValueError("Callback key must not be empty")
        return _encode(
            [
                self.prefix,
                self.token,
                self.key,
                str(max(0, int(self.page))),
            ]
        )

    @classmethod
    def parse(cls, raw: str | None, *, prefix: str) -> "KeyedPageCallback | None":
        parts = (raw or "").split(":")
        if len(parts) != 4 or parts[0] != prefix:
            return None
        page = _non_negative(parts[3])
        if page is None or not parts[1] or not parts[2]:
            return None
        return cls(prefix, parts[1], parts[2], page)


@dataclass(frozen=True, slots=True)
class EpisodeDetailCallback:
    token: str
    backend: str
    episode_number: int
    return_page: int

    prefix = "ae"

    def encode(self) -> str:
        if not self.backend:
            raise ValueError("Episode backend must not be empty")
        return _encode(
            [
                self.prefix,
                self.token,
                self.backend,
                str(max(1, int(self.episode_number))),
                str(max(0, int(self.return_page))),
            ]
        )

    @classmethod
    def parse(cls, raw: str | None) -> "EpisodeDetailCallback | None":
        parts = (raw or "").split(":")
        # Oldest payload omitted the backend and implicitly selected index 0.
        if len(parts) == 4 and parts[0] == cls.prefix:
            episode = _non_negative(parts[2])
            page = _non_negative(parts[3])
            if episode is None or episode <= 0 or page is None or not parts[1]:
                return None
            return cls(parts[1], "0", episode, page)
        if len(parts) != 5 or parts[0] != cls.prefix:
            return None
        episode = _non_negative(parts[3])
        page = _non_negative(parts[4])
        if (
            episode is None
            or episode <= 0
            or page is None
            or not parts[1]
            or not parts[2]
        ):
            return None
        return cls(parts[1], parts[2], episode, page)


@dataclass(frozen=True, slots=True)
class TokenCallback:
    prefix: str
    token: str

    def encode(self) -> str:
        return _encode([self.prefix, self.token])

    @classmethod
    def parse(cls, raw: str | None, *, prefix: str) -> "TokenCallback | None":
        parts = (raw or "").split(":")
        if len(parts) != 2 or parts[0] != prefix or not parts[1]:
            return None
        return cls(prefix, parts[1])


@dataclass(frozen=True, slots=True)
class TokenValueCallback:
    prefix: str
    token: str
    value: str

    def encode(self) -> str:
        return _encode([self.prefix, self.token, self.value])

    @classmethod
    def parse(cls, raw: str | None, *, prefix: str) -> "TokenValueCallback | None":
        parts = (raw or "").split(":")
        if len(parts) != 3 or parts[0] != prefix or not parts[1] or not parts[2]:
            return None
        return cls(prefix, parts[1], parts[2])


@dataclass(frozen=True, slots=True)
class TokenIndexCallback:
    prefix: str
    token: str
    index: int

    def encode(self) -> str:
        return _encode([self.prefix, self.token, str(max(0, int(self.index)))])

    @classmethod
    def parse(cls, raw: str | None, *, prefix: str) -> "TokenIndexCallback | None":
        parts = (raw or "").split(":")
        if len(parts) != 3 or parts[0] != prefix or not parts[1]:
            return None
        index = _non_negative(parts[2])
        if index is None:
            return None
        return cls(prefix, parts[1], index)


@dataclass(frozen=True, slots=True)
class SettingsCallback:
    action: str
    value: str | None = None

    prefix = "settings"

    def encode(self) -> str:
        parts = [self.prefix, self.action]
        if self.value is not None:
            parts.append(self.value)
        return _encode(parts)

    @classmethod
    def parse(cls, raw: str | None) -> "SettingsCallback | None":
        parts = (raw or "").split(":")
        if len(parts) not in {2, 3} or parts[0] != cls.prefix or not parts[1]:
            return None
        if len(parts) == 3 and not parts[2]:
            return None
        return cls(parts[1], parts[2] if len(parts) == 3 else None)
