from __future__ import annotations

import html

from bots.telegram.card.rendering import _table_html, append_block, format_number
from core.models import PopularityStats
from localization import text


_POPULARITY_STATUS_ORDER = (
    "watching",
    "completed",
    "planned",
    "on_hold",
    "dropped",
    "rewatching",
)


def _popularity_metric_lines(stats: PopularityStats, *, locale: str) -> list[str]:
    lines: list[str] = []
    if stats.rank is not None:
        lines.append(text("card", "rank", locale=locale, value=stats.rank))
    if stats.popularity_rank is not None:
        lines.append(
            text("card", "popularity", locale=locale, value=stats.popularity_rank)
        )
    if stats.list_users is not None:
        lines.append(
            text(
                "card",
                "list_users",
                locale=locale,
                value=format_number(stats.list_users),
            )
        )
    if stats.scoring_users is not None:
        lines.append(
            text(
                "card",
                "scoring_users",
                locale=locale,
                value=format_number(stats.scoring_users),
            )
        )
    if stats.favorites is not None:
        lines.append(
            text(
                "card",
                "favorites",
                locale=locale,
                value=format_number(stats.favorites),
            )
        )
    return lines


def _popularity_status_lines(stats: PopularityStats, *, locale: str) -> list[str]:
    lines: list[str] = []
    seen: set[str] = set()
    for key in _POPULARITY_STATUS_ORDER:
        if key not in stats.status_distribution:
            continue
        seen.add(key)
        label = text("user_list_status", key, locale=locale, default=key)
        lines.append(f"{label}: {format_number(stats.status_distribution[key])}")
    for key in sorted(set(stats.status_distribution) - seen):
        label = text("user_list_status", key, locale=locale, default=key)
        lines.append(f"{label}: {format_number(stats.status_distribution[key])}")
    return lines


def _popularity_score_lines(stats: PopularityStats) -> list[str]:
    return [
        f"{score}/10: {format_number(count)}"
        for score, count in sorted(stats.score_distribution.items(), reverse=True)
    ]


def _popularity_ranking_lines(stats: PopularityStats, *, locale: str) -> list[str]:
    lines: list[str] = []
    for item in stats.rankings:
        # All-time rated/popular positions are already shown in the summary rows.
        if item.all_time and item.kind in {"rated", "popular"}:
            continue
        kind = text("ranking_kind", item.kind, locale=locale, default=item.kind)
        if item.season and item.year:
            season = text("season", item.season, locale=locale, default=item.season)
            period = f"{season} {item.year}"
        elif item.year:
            period = str(item.year)
        elif item.all_time:
            period = text("card", "all_time", locale=locale)
        else:
            period = text("card", "other_period", locale=locale)
        lines.append(f"{kind} — {period}: #{item.rank}")
    return lines


def format_popularity(source: str, stats: PopularityStats, *, locale: str) -> str:
    lines = [text("card", "popularity_title", locale=locale, source=source)]
    append_block(
        lines,
        text("card", "popularity_metrics", locale=locale),
        _popularity_metric_lines(stats, locale=locale),
    )
    append_block(
        lines,
        text("card", "popularity_statuses", locale=locale),
        _popularity_status_lines(stats, locale=locale),
    )
    append_block(
        lines,
        text("card", "popularity_scores", locale=locale),
        _popularity_score_lines(stats),
    )
    append_block(
        lines,
        text("card", "popularity_rankings", locale=locale),
        _popularity_ranking_lines(stats, locale=locale),
    )
    return "\n".join(lines)


def _popularity_tables_html(
    source: str,
    stats: PopularityStats,
    *,
    locale: str,
) -> str:
    title_html = f"<h2>{html.escape(text('card', 'popularity_title', locale=locale, source=source))}</h2>"
    tables = "".join(
        _table_html(caption, rows)
        for caption, rows in (
            (
                text("card", "popularity_metrics", locale=locale),
                _popularity_metric_lines(stats, locale=locale),
            ),
            (
                text("card", "popularity_statuses", locale=locale),
                _popularity_status_lines(stats, locale=locale),
            ),
            (
                text("card", "popularity_scores", locale=locale),
                _popularity_score_lines(stats),
            ),
            (
                text("card", "popularity_rankings", locale=locale),
                _popularity_ranking_lines(stats, locale=locale),
            ),
        )
        if rows
    )
    if not tables:
        return (
            title_html
            + f"<p>{html.escape(text('common', 'no_data', locale=locale))}</p>"
        )
    return title_html + tables
