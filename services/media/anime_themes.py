from __future__ import annotations

import time
from typing import Protocol

from core.anime_themes import AnimeThemeEntry
from core.identity import AnimeIdentity
from core.runtime_metrics import get_runtime_metrics


class AnimeThemeSource(Protocol):
    name: str
    display_name: str

    def supports_identity(self, identity: AnimeIdentity) -> bool: ...

    async def load_themes(self, identity: AnimeIdentity) -> list[AnimeThemeEntry]: ...


def _theme_key(theme: AnimeThemeEntry) -> tuple[str, str]:
    return theme.kind, theme.source_theme_id or theme.slug.casefold()


def _dedupe_prefer_latest_version(
    values: list[AnimeThemeEntry],
) -> list[AnimeThemeEntry]:
    selected: dict[tuple[str, str], AnimeThemeEntry] = {}
    for theme in values:
        key = _theme_key(theme)
        previous = selected.get(key)
        if previous is None or (theme.version or 0) > (previous.version or 0):
            selected[key] = theme
    return list(selected.values())


class AnimeThemeService:
    """Resolve AnimeThemes entries that are relevant to one concrete episode."""

    def __init__(self, source: AnimeThemeSource) -> None:
        self.source = source

    def supports_identity(self, identity: AnimeIdentity) -> bool:
        return self.source.supports_identity(identity)

    async def load_episode_themes(
        self,
        identity: AnimeIdentity,
        episode_number: int,
    ) -> list[AnimeThemeEntry]:
        wanted = int(episode_number)
        if wanted <= 0 or not self.supports_identity(identity):
            return []

        metrics = get_runtime_metrics()
        started = time.monotonic()
        try:
            themes = await self.source.load_themes(identity)
        except Exception:
            if metrics is not None:
                metrics.record_source_call(
                    "animethemes",
                    outcome="error",
                    duration_ms=(time.monotonic() - started) * 1000,
                )
            raise
        if metrics is not None:
            metrics.record_source_call(
                "animethemes",
                outcome="success",
                duration_ms=(time.monotonic() - started) * 1000,
            )
        result: list[AnimeThemeEntry] = []
        for kind in ("opening", "ending"):
            kind_values = [theme for theme in themes if theme.kind == kind]
            explicit = [
                theme for theme in kind_values if theme.applies_to_episode(wanted)
            ]
            if explicit:
                result.extend(_dedupe_prefer_latest_version(explicit))
                continue

            # A blank AnimeThemes episode scope is common in older records. Use
            # it only when it identifies one unambiguous theme for this kind.
            unscoped = [
                theme
                for theme in kind_values
                if not theme.has_explicit_episode_scope and not theme.spoiler
            ]
            distinct = {_theme_key(theme) for theme in unscoped}
            if len(distinct) == 1:
                result.extend(_dedupe_prefer_latest_version(unscoped))

        result.sort(
            key=lambda theme: (
                0 if theme.kind == "opening" else 1,
                theme.sequence if theme.sequence is not None else 10_000,
                theme.slug.casefold(),
                theme.version or 0,
            )
        )
        return result
