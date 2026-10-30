from __future__ import annotations

from dataclasses import dataclass, field

from core.models import SearchCandidate


class ImageSearchQuotaExhausted(RuntimeError):
    """Raised when an image-search provider has no usable daily/search quota."""


@dataclass(frozen=True, slots=True)
class ImageSearchInput:
    """One image supplied either as a public URL or downloaded Telegram bytes."""

    url: str | None = None
    content: bytes | None = None
    filename: str = "image.jpg"
    content_type: str = "image/jpeg"

    def __post_init__(self) -> None:
        if bool(self.url) == bool(self.content):
            raise ValueError("ImageSearchInput requires exactly one of url or content")


@dataclass(frozen=True, slots=True)
class ImageSearchAvailability:
    provider_key: str
    display_name: str
    available: bool
    remaining: int | None = None
    limit: int | None = None


@dataclass(frozen=True, slots=True)
class ImageSearchMatch:
    provider_key: str
    provider_name: str
    anilist_id: str
    similarity: float
    episode: str | None = None
    from_seconds: float | None = None
    to_seconds: float | None = None
    preview_image: str | None = None
    preview_video: str | None = None
    titles: dict[str, str] = field(default_factory=dict)
    aliases: tuple[str, ...] = ()
    mal_id: str | None = None


@dataclass(slots=True)
class ImageSearchCandidate:
    candidate: SearchCandidate
    matches: list[ImageSearchMatch] = field(default_factory=list)


@dataclass(slots=True)
class ImageSearchResultSet:
    items: list[ImageSearchCandidate]
    errors: dict[str, str] = field(default_factory=dict)
