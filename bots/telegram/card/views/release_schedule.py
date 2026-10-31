from __future__ import annotations

from core.models import AggregatedAnime, EpisodeReleaseProjection
from localization import text


def _release_value(item: EpisodeReleaseProjection) -> str:
    return item.airs_at.isoformat()


def format_release_projection(item: EpisodeReleaseProjection, *, locale: str) -> str:
    value = _release_value(item)
    if item.episode_number is None:
        key = (
            "release_schedule_estimated_unknown"
            if item.estimated
            else "release_schedule_source_unknown"
        )
        return text("card", key, locale=locale, value=value)
    key = (
        "release_schedule_estimated_item"
        if item.estimated
        else "release_schedule_source_item"
    )
    return text(
        "card",
        key,
        locale=locale,
        episode=item.episode_number,
        value=value,
    )


def format_release_schedule(anime: AggregatedAnime, *, locale: str) -> str:
    title = text("card", "release_schedule_title", locale=locale)
    if not anime.episode_release_schedule:
        return f"{title}:\n{text('card', 'release_schedule_empty', locale=locale)}"

    lines = [f"{title}:"]
    lines.extend(
        format_release_projection(item, locale=locale)
        for item in anime.episode_release_schedule
    )

    if any(item.estimated for item in anime.episode_release_schedule):
        lines.extend(
            ["", text("card", "release_schedule_estimate_note", locale=locale)]
        )
    return "\n".join(lines)
