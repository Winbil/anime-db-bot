from __future__ import annotations

import html
import logging

from aiogram.types import InlineKeyboardMarkup, InputRichMessage, Message

from bots.telegram.callbacks import resolve_key_or_legacy_index
from bots.telegram.card.constants import RICH_MESSAGE_LIMIT, STANDARD_MESSAGE_LIMIT
from bots.telegram.card.keyboards import (
    description_keyboard,
    fallback_main_keyboard,
    navigation_keyboard,
    source_section_keyboard,
)
from bots.telegram.card.selectors import (
    description_source_options,
    ordered_mapping_items,
    source_section_options,
)
from core.canonicalization import display_person_name, localize_role_token
from core.models import AggregatedAnime, BroadcastSlot, PopularityStats
from core.source_keys import SourceKey
from core.source_names import MAL_SOURCE_NAME
from core.temporal import format_time
from localization import text


def split_text(text_value: str, limit: int, *, locale: str = "ru") -> list[str]:
    text_value = text_value.strip()
    if not text_value:
        return [text("common", "no_data", locale=locale)]
    if len(text_value) <= limit:
        return [text_value]

    chunks: list[str] = []
    while len(text_value) > limit:
        split_at = text_value.rfind("\n\n", 0, limit)
        if split_at < limit // 2:
            split_at = text_value.rfind("\n", 0, limit)
        if split_at < limit // 2:
            split_at = text_value.rfind(" ", 0, limit)
        if split_at < limit // 2:
            split_at = limit
        chunks.append(text_value[:split_at].strip())
        text_value = text_value[split_at:].strip()

    if text_value:
        chunks.append(text_value)
    return chunks


def plain_text_to_rich_html(text_value: str) -> str:
    paragraphs: list[str] = []
    for paragraph in text_value.split("\n\n"):
        escaped = html.escape(paragraph).replace("\n", "<br>")
        if escaped:
            paragraphs.append(f"<p>{escaped}</p>")
    return "".join(paragraphs)


def poster_html(anime: AggregatedAnime) -> str:
    urls = anime.posters[:50]
    if not urls:
        return ""
    images = "".join(f'<img src="{html.escape(url, quote=True)}"/>' for url in urls)
    return images if len(urls) == 1 else f"<tg-slideshow>{images}</tg-slideshow>"


def rich(text_value: str) -> InputRichMessage:
    return InputRichMessage(html=plain_text_to_rich_html(text_value))


def display_anime_title(anime: AggregatedAnime, locale: str) -> str:
    if locale == "en":
        order = ("english", "romaji", "japanese", "russian", "licensed_ru")
    else:
        order = ("russian", "licensed_ru", "romaji", "english", "japanese")
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


def _table_html(caption: str, lines: list[str]) -> str:
    rows: list[str] = []
    for rendered in lines:
        rendered = (rendered or "").strip()
        if not rendered:
            continue
        label, separator, value = rendered.partition(":")
        if separator and label.strip():
            rows.append(
                "<tr>"
                f'<th align="left" valign="top">{html.escape(label.strip())}</th>'
                f'<td align="left" valign="top">{html.escape(value.strip())}</td>'
                "</tr>"
            )
        else:
            rows.append(
                f'<tr><td colspan="2" align="left">{html.escape(rendered)}</td></tr>'
            )

    if not rows:
        return ""
    return (
        "<table bordered striped compact>"
        f"<caption><b>{html.escape(caption)}</b></caption>" + "".join(rows) + "</table>"
    )


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
        + button("trailers_button", "trailers")
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


async def edit_standard_text(
    message: Message,
    text_value: str,
    reply_markup: InlineKeyboardMarkup | None = None,
    *,
    locale: str = "ru",
    limit: int = STANDARD_MESSAGE_LIMIT,
) -> None:
    """Edit the callback message without discarding overflow text.

    The keyboard remains on the edited message so subsequent callbacks keep
    targeting one stable message. Overflow chunks are emitted as plain follow-up
    messages instead of being silently truncated.
    """
    chunks = split_text(text_value, limit, locale=locale)
    await message.edit_text(text=chunks[0], reply_markup=reply_markup)
    for chunk in chunks[1:]:
        await message.answer(chunk)


async def send_standard_text(
    message: Message,
    text_value: str,
    reply_markup: InlineKeyboardMarkup | None = None,
    *,
    locale: str = "ru",
) -> None:
    chunks = split_text(text_value, STANDARD_MESSAGE_LIMIT, locale=locale)
    for index, chunk in enumerate(chunks):
        await message.answer(
            chunk,
            reply_markup=reply_markup if index == len(chunks) - 1 else None,
        )


def dedupe_strings(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        value = (value or "").strip()
        key = value.casefold()
        if value and key not in seen:
            seen.add(key)
            result.append(value)
    return result


def format_number(value: int | None) -> str | None:
    if value is None:
        return None
    return f"{value:,}".replace(",", " ")


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


def format_people(title: str, people, *, locale: str) -> str:
    if not people:
        return f"{title}:\n{text('common', 'no_data', locale=locale)}"
    lines = [f"{title}:"]
    for person in people:
        roles = ", ".join(
            localize_role_token(role, locale=locale)
            for role in person.roles
            if localize_role_token(role, locale=locale)
        ) or text("common", "role_not_specified", locale=locale)
        name = display_person_name(person.name, person.aliases, locale=locale)
        lines.append(f"• {name} — {roles}")
    return "\n".join(lines)


def _title_rows(
    titles_map: dict[str, str],
    synonyms_values: list[str],
    *,
    locale: str,
) -> list[tuple[str, str]]:
    labels = {
        "russian": text("card", "title_russian", locale=locale),
        "romaji": text("card", "title_romaji", locale=locale),
        "english": text("card", "title_english", locale=locale),
        "japanese": text("card", "title_japanese", locale=locale),
        "licensed_ru": text("card", "title_licensed_ru", locale=locale),
    }
    rows: list[tuple[str, str]] = []
    seen_titles: set[str] = set()
    for key in ("russian", "romaji", "english", "japanese", "licensed_ru"):
        value = (titles_map.get(key) or "").strip()
        if value and value.casefold() not in seen_titles:
            seen_titles.add(value.casefold())
            rows.append((labels[key], value))

    synonyms = [
        value
        for value in dedupe_strings(synonyms_values)
        if value.casefold() not in seen_titles
    ]
    if synonyms:
        rows.append((text("card", "synonyms", locale=locale), "; ".join(synonyms)))
    return rows


def _titles_table_html(
    titles_map: dict[str, str],
    synonyms_values: list[str],
    *,
    locale: str,
    source: str | None = None,
) -> str:
    base_title = text("card", "titles", locale=locale)
    caption = f"{base_title} — {source}" if source else base_title
    rows = _title_rows(titles_map, synonyms_values, locale=locale)
    if not rows:
        return (
            f"<h2>{html.escape(caption)}</h2>"
            f"<p>{html.escape(text('common', 'no_data', locale=locale))}</p>"
        )
    cells = "".join(
        "<tr>"
        f'<th align="left" valign="top">{html.escape(label)}</th>'
        f'<td align="left" valign="top">{html.escape(value)}</td>'
        "</tr>"
        for label, value in rows
    )
    return (
        "<table bordered striped compact>"
        f"<caption><b>{html.escape(caption)}</b></caption>"
        f"{cells}</table>"
    )


def format_titles(
    titles_map: dict[str, str],
    synonyms_values: list[str],
    *,
    locale: str,
    source: str | None = None,
) -> str:
    base_title = text("card", "titles", locale=locale)
    title_value = f"{base_title} — {source}:" if source else f"{base_title}:"
    lines = [title_value]
    for label, value in _title_rows(titles_map, synonyms_values, locale=locale):
        lines.append(f"• {label}: {value}")

    if len(lines) == 1:
        lines.append(text("common", "no_data", locale=locale))
    return "\n".join(lines)


def append_block(target: list[str], title_value: str, lines: list[str]) -> None:
    lines = [line for line in lines if line]
    if not lines:
        return
    if target:
        target.append("")
    target.append(f"{title_value}:")
    target.extend(lines)


def source_section_text(
    anime: AggregatedAnime,
    section: str,
    source: str,
    *,
    locale: str,
) -> str:
    if section == "titles":
        return format_titles(
            anime.titles_by_source.get(source, {}),
            anime.synonyms_by_source.get(source, []),
            source=source,
            locale=locale,
        )
    if section == "staff":
        return format_people(
            f"{text('card', 'staff', locale=locale)} — {source}",
            anime.staff_by_source.get(source, []),
            locale=locale,
        )
    if section == "voices":
        return format_people(
            f"{text('card', 'voices', locale=locale)} — {source}",
            anime.voices_by_source.get(source, []),
            locale=locale,
        )
    if section == "popularity":
        stats = anime.popularity_by_source.get(source)
        if stats is not None and stats.has_data():
            return format_popularity(source, stats, locale=locale)
    return text("common", "no_data", locale=locale)


def anime_sections(anime: AggregatedAnime, *, locale: str = "ru") -> dict[str, str]:
    description_text = text(
        "card",
        "description_choose" if anime.descriptions else "description_empty",
        locale=locale,
    )
    links_text = text(
        "card",
        "links_choose" if anime.urls else "links_empty",
        locale=locale,
    )
    popularity_text = text(
        "card",
        "popularity_choose" if anime.popularity_by_source else "popularity_empty",
        locale=locale,
    )

    return {
        "main": _main_text(anime, locale=locale),
        "titles": format_titles(anime.titles, anime.synonyms, locale=locale),
        "description": description_text,
        "popularity": popularity_text,
        "links": links_text,
        "staff": format_people(
            text("card", "staff", locale=locale), anime.staff, locale=locale
        ),
        "voices": format_people(
            text("card", "voices", locale=locale), anime.voices, locale=locale
        ),
    }


def view_pages(anime: AggregatedAnime, section: str, *, locale: str) -> list[str]:
    return split_text(
        anime_sections(anime, locale=locale).get(section)
        or text("common", "no_data", locale=locale),
        RICH_MESSAGE_LIMIT,
        locale=locale,
    )


def rich_view(
    token: str,
    anime: AggregatedAnime,
    section: str,
    text_value: str,
    *,
    locale: str,
) -> InputRichMessage:
    if section == "main":
        return main_rich(token, anime, text_value, locale=locale)
    if section == "titles":
        full_titles = format_titles(anime.titles, anime.synonyms, locale=locale)
        if text_value.strip() == full_titles.strip():
            return InputRichMessage(
                html=_titles_table_html(anime.titles, anime.synonyms, locale=locale)
            )
    return rich(text_value)


async def send_anime_view(
    message: Message,
    token: str,
    anime: AggregatedAnime,
    section: str = "main",
    page: int = 0,
    *,
    locale: str,
) -> None:
    pages = view_pages(anime, section, locale=locale)
    page = max(0, min(page, len(pages) - 1))
    keyboard = navigation_keyboard(
        token, anime, section, page, len(pages), locale=locale
    )
    text_value = pages[page]

    try:
        await message.answer_rich(
            rich_view(token, anime, section, text_value, locale=locale),
            reply_markup=keyboard,
        )
    except Exception:
        logging.exception(
            "sendRichMessage failed; falling back to standard sendMessage"
        )
        fallback = (
            fallback_main_keyboard(token, locale=locale)
            if section == "main"
            else keyboard
        )
        await send_standard_text(
            message, text_value, reply_markup=fallback, locale=locale
        )


async def edit_anime_view(
    message: Message,
    token: str,
    anime: AggregatedAnime,
    section: str,
    page: int,
    *,
    locale: str,
) -> None:
    pages = view_pages(anime, section, locale=locale)
    page = max(0, min(page, len(pages) - 1))
    keyboard = navigation_keyboard(
        token, anime, section, page, len(pages), locale=locale
    )
    text_value = pages[page]

    try:
        await message.edit_text(
            rich_message=rich_view(token, anime, section, text_value, locale=locale),
            reply_markup=keyboard,
        )
    except Exception:
        logging.exception(
            "Rich message edit failed; falling back to standard text edit"
        )
        fallback = (
            fallback_main_keyboard(token, locale=locale)
            if section == "main"
            else keyboard
        )
        await edit_standard_text(
            message,
            text_value,
            reply_markup=fallback,
            locale=locale,
        )


async def edit_description_view(
    message: Message,
    token: str,
    anime: AggregatedAnime,
    source_key: str,
    page: int,
    *,
    locale: str,
) -> None:
    options = description_source_options(anime)
    keys = [key for key, _ in options]
    source_key = resolve_key_or_legacy_index(source_key, keys)
    source = dict(options)[source_key]
    description = anime.descriptions[source]
    text_value = (
        text("card", "description_title", locale=locale, source=source)
        + f"\n\n{description}"
    )
    if source in {"MyAnimeList", "MAL (MyAnimeList) / Jikan"} and anime.background:
        text_value += (
            f"\n\n{text('card', 'extra_info', locale=locale)}\n{anime.background}"
        )

    pages = split_text(text_value, RICH_MESSAGE_LIMIT, locale=locale)
    page = max(0, min(page, len(pages) - 1))
    keyboard = description_keyboard(token, source_key, page, len(pages), locale=locale)

    try:
        await message.edit_text(
            rich_message=rich(pages[page]),
            reply_markup=keyboard,
        )
    except Exception:
        logging.exception(
            "Rich description edit failed; falling back to standard text edit"
        )
        await edit_standard_text(
            message,
            pages[page],
            reply_markup=keyboard,
            locale=locale,
        )


async def edit_source_section_view(
    message: Message,
    token: str,
    anime: AggregatedAnime,
    section: str,
    source_key: str,
    page: int,
    *,
    locale: str,
) -> None:
    options = source_section_options(anime, section)
    keys = [key for key, _ in options]
    source_key = resolve_key_or_legacy_index(source_key, keys)
    source = dict(options)[source_key]
    section_text = source_section_text(anime, section, source, locale=locale)
    pages = split_text(
        section_text,
        RICH_MESSAGE_LIMIT,
        locale=locale,
    )
    page = max(0, min(page, len(pages) - 1))
    keyboard = source_section_keyboard(
        token,
        anime,
        section,
        source_key,
        page,
        len(pages),
        locale=locale,
    )

    if section == "titles" and len(pages) == 1:
        rich_message = InputRichMessage(
            html=_titles_table_html(
                anime.titles_by_source.get(source, {}),
                anime.synonyms_by_source.get(source, []),
                source=source,
                locale=locale,
            )
        )
    elif section == "popularity" and len(pages) == 1:
        stats = anime.popularity_by_source.get(source)
        rich_message = InputRichMessage(
            html=(
                _popularity_tables_html(source, stats, locale=locale)
                if stats is not None
                else plain_text_to_rich_html(pages[page])
            )
        )
    else:
        rich_message = rich(pages[page])

    try:
        await message.edit_text(
            rich_message=rich_message,
            reply_markup=keyboard,
        )
    except Exception:
        logging.exception(
            "Rich source section edit failed; falling back to standard text edit"
        )
        await edit_standard_text(
            message,
            pages[page],
            reply_markup=keyboard,
            locale=locale,
        )
