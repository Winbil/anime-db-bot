from __future__ import annotations

import html

from aiogram.types import InputRichMessage

from bots.telegram.card.views.rendering import (
    _table_html,
    append_block,
    plain_text_to_rich_html,
    poster_html,
)
from bots.telegram.card.ui.selectors import ordered_mapping_items
from core.models import AggregatedAnime, BroadcastSlot
from core.source_keys import SourceKey
from core.source_names import MAL_SOURCE_NAME
from core.temporal import format_time
from localization import text


def display_anime_title(anime: AggregatedAnime, locale: str) -> str:
    if locale == "ja":
        order = ("japanese", "romaji", "english", "russian", "licensed_ru")
    elif locale == "ru":
        order = ("russian", "licensed_ru", "romaji", "english", "japanese")
    else:
        order = ("english", "romaji", "japanese", "russian", "licensed_ru")
    for key in order:
        value = (anime.titles.get(key) or "").strip()
        if value:
            return value
    return anime.title


def _domain(domain: str, value: str | None, locale: str) -> str | None:
    if not value:
        return None
    return text(domain, value, locale=locale, default=value)


def _season(anime: AggregatedAnime, locale: str) -> str | None:
    value = _domain("season", anime.season, locale)
    if anime.season_year:
        return " ".join(part for part in (value, str(anime.season_year)) if part)
    return value


def _broadcast(item: BroadcastSlot, locale: str) -> str:
    weekday = _domain("weekday", item.weekday, locale) if item.weekday else None
    return " ".join(part for part in (weekday, format_time(item.time)) if part)


def _quick_actions_html(token: str, *, locale: str) -> str:
    token_value = html.escape(token, quote=True)

    def button(label_key: str, section: str) -> str:
        return (
            f'<tg-button type="callback_data" data="av:{token_value}:{section}:0">'
            f"{html.escape(text('card', label_key, locale=locale))}"
            "</tg-button>"
        )

    return (
        f"<h3>{html.escape(text('card', 'details', locale=locale))}</h3>"
        '<tg-button-row align="left">'
        + button("description_button", "description")
        + button("popularity_button", "popularity")
        + button("episodes_button", "episodes")
        + "</tg-button-row>"
        '<tg-button-row align="left">'
        + button("staff_button", "staff")
        + button("voices_button", "voices")
        + button("characters_button", "characters")
        + "</tg-button-row>"
        '<tg-button-row align="left">'
        + button("titles_button", "titles")
        + button("screenshots_button", "screenshots")
        + button("trailers_button", "trailers")
        + "</tg-button-row>"
        '<tg-button-row align="left">'
        + button("links_button", "links")
        + "</tg-button-row>"
        "<hr/>"
    )


def _source_identity_key(source_name: str) -> str | None:
    normalized = " ".join((source_name or "").split()).strip().casefold()
    if normalized in {MAL_SOURCE_NAME.casefold(), "myanimelist"}:
        return SourceKey.MAL.value
    try:
        return SourceKey(normalized).value
    except ValueError:
        return None


def _card_source_ids(anime: AggregatedAnime) -> list[tuple[str, str]]:
    """Return IDs only for metadata sources that actually contributed a record.

    ``anime.external_ids`` intentionally keeps the full resolved identity graph so
    mapping-only IDs remain available to second-pass and lazy capabilities. The
    main card should not present those resolver edges as if their databases had
    actually supplied metadata, so rendering is scoped to ``anime.sources``.
    """
    result: list[tuple[str, str]] = []
    seen: set[str] = set()
    for source_name in anime.sources:
        source_key = _source_identity_key(source_name)
        if source_key is None or source_key in seen:
            continue
        external_id = anime.external_ids.get(source_key)
        if not external_id:
            continue
        seen.add(source_key)
        result.append((source_key, external_id))
    return result


def _main_blocks(anime: AggregatedAnime, *, locale: str) -> list[tuple[str, list[str]]]:
    total = anime.episodes_total or 0
    aired = anime.episodes_aired or 0
    episodes = f"{aired}/{total}" if total else str(aired or "—")

    basic: list[str] = []
    kind = _domain("anime_kind", anime.kind, locale)
    status = _domain("anime_status", anime.status, locale)
    rating = _domain("rating", anime.rating, locale)
    if kind:
        basic.append(text("card", "type", locale=locale, value=kind))
    if status:
        basic.append(text("card", "status", locale=locale, value=status))
    basic.append(text("card", "episodes", locale=locale, value=episodes))
    if anime.duration_minutes:
        basic.append(
            text("card", "duration", locale=locale, minutes=anime.duration_minutes)
        )
    if rating:
        basic.append(text("card", "rating", locale=locale, value=rating))

    release: list[str] = []
    season = _season(anime, locale)
    if season:
        release.append(text("card", "season", locale=locale, value=season))
    if anime.aired_on or anime.released_on:
        release.append(
            text(
                "card",
                "air_dates",
                locale=locale,
                start=anime.aired_on.isoformat() if anime.aired_on else "—",
                end=anime.released_on.isoformat() if anime.released_on else "—",
            )
        )
    if anime.next_episode_at:
        release.append(
            text(
                "card",
                "next_episode",
                locale=locale,
                value=anime.next_episode_at.isoformat(),
            )
        )
    if anime.broadcasts:
        broadcast_text = ", ".join(
            value for item in anime.broadcasts if (value := _broadcast(item, locale))
        )
        if broadcast_text:
            release.append(
                text("card", "broadcast", locale=locale, value=broadcast_text)
            )

    production: list[str] = []
    if anime.source_materials:
        values = ", ".join(
            text("source_material", value, locale=locale, default=value)
            for value in anime.source_materials
        )
        production.append(text("card", "source_material", locale=locale, value=values))
    if anime.genres:
        values = ", ".join(
            text("genres", value, locale=locale, default=value)
            for value in anime.genres
        )
        production.append(text("card", "genres", locale=locale, value=values))
    if anime.studios:
        production.append(
            text("card", "studios", locale=locale, value=", ".join(anime.studios))
        )
    if anime.licensors:
        production.append(
            text("card", "licensors", locale=locale, value=", ".join(anime.licensors))
        )
    if anime.franchise:
        production.append(
            text("card", "franchise", locale=locale, value=anime.franchise)
        )

    score_lines: list[str] = []
    if anime.score_average is not None:
        score_lines.append(
            text(
                "card",
                "average_score",
                locale=locale,
                score=f"{anime.score_average:g}",
                count=anime.score_sources_count,
            )
        )
    for source, score in ordered_mapping_items(anime.scores, anime.sources):
        score_lines.append(f"{source}: {float(score):g}")

    source_lines: list[str] = []
    if anime.sources:
        source_lines.append(
            text("card", "databases", locale=locale, value=", ".join(anime.sources))
        )
    card_source_ids = _card_source_ids(anime)
    if card_source_ids:
        ids = " | ".join(f"{name.upper()}: {value}" for name, value in card_source_ids)
        source_lines.append(text("card", "ids", locale=locale, value=ids))
    if anime.errors:
        source_lines.append(
            text("card", "unavailable", locale=locale, value=", ".join(anime.errors))
        )

    return [
        (text("card", "block_main", locale=locale), basic),
        (text("card", "block_release", locale=locale), release),
        (text("card", "block_production", locale=locale), production),
        (text("card", "block_score", locale=locale), score_lines),
        (text("card", "block_sources", locale=locale), source_lines),
    ]


def _main_text(anime: AggregatedAnime, *, locale: str) -> str:
    main = [display_anime_title(anime, locale)]
    for title_value, lines in _main_blocks(anime, locale=locale):
        append_block(main, title_value, lines)
    return "\n".join(main)


def main_rich(
    token: str,
    anime: AggregatedAnime,
    text_value: str,
    *,
    locale: str,
) -> InputRichMessage:
    full_main = _main_text(anime, locale=locale)
    if text_value.strip() != full_main.strip():
        return InputRichMessage(
            html=poster_html(anime) + plain_text_to_rich_html(text_value)
        )

    tables = "".join(
        _table_html(title_value, lines)
        for title_value, lines in _main_blocks(anime, locale=locale)
        if lines
    )
    title_html = f"<h2>{html.escape(display_anime_title(anime, locale))}</h2>"
    return InputRichMessage(
        html=(
            poster_html(anime)
            + title_html
            + _quick_actions_html(token, locale=locale)
            + tables
        )
    )
