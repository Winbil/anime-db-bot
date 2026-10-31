from __future__ import annotations

from core.models import AggregatedAnime, EpisodeReleaseProjection
from localization import text


def _release_value(item: EpisodeReleaseProjection) -> str:
    return item.airs_at.isoformat()


def format_release_schedule(anime: AggregatedAnime, *, locale: str) -> str:
    title = text("card", "release_schedule_title", locale=locale)
    if not anime.episode_release_schedule:
        return f"{title}:\n{text('card', 'release_schedule_empty', locale=locale)}"

    lines = [f"{title}:"]
    for item in anime.episode_release_schedule:
        value = _release_value(item)
        if item.episode_number is None:
            key = (
                "release_schedule_estimated_unknown"
                if item.estimated
                else "release_schedule_source_unknown"
            )
            lines.append(text("card", key, locale=locale, value=value))
            continue
        key = (
            "release_schedule_estimated_item"
            if item.estimated
            else "release_schedule_source_item"
        )
        lines.append(
            text(
                "card",
                key,
                locale=locale,
                episode=item.episode_number,
                value=value,
            )
        )

    if any(item.estimated for item in anime.episode_release_schedule):
        lines.extend(
            ["", text("card", "release_schedule_estimate_note", locale=locale)]
        )
    return "\n".join(lines)
