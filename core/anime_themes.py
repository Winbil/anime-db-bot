from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AnimeThemeEntry:
    """One AnimeThemes OP/ED entry normalized for episode-level use."""

    kind: str
    slug: str
    title: str | None = None
    artists: tuple[str, ...] = ()
    sequence: int | None = None
    episodes: str | None = None
    episode_ranges: tuple[tuple[int, int], ...] = ()
    version: int | None = None
    video_url: str | None = None
    source_theme_id: str | None = None
    source_entry_id: str | None = None
    spoiler: bool = False

    @property
    def label(self) -> str:
        if self.slug:
            return self.slug.upper()
        prefix = "OP" if self.kind == "opening" else "ED"
        return f"{prefix}{self.sequence}" if self.sequence is not None else prefix

    @property
    def has_explicit_episode_scope(self) -> bool:
        return bool((self.episodes or "").strip())

    def applies_to_episode(self, episode_number: int) -> bool:
        wanted = int(episode_number)
        if wanted <= 0:
            return False
        return any(start <= wanted <= end for start, end in self.episode_ranges)
