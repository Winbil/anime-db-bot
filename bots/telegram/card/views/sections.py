from __future__ import annotations

import html

from aiogram.types import InputRichMessage

from bots.telegram.card.ui.constants import RICH_MESSAGE_LIMIT
from bots.telegram.card.views.main import _main_text, main_rich
from bots.telegram.card.views.popularity import format_popularity
from bots.telegram.card.views.rendering import (
    dedupe_strings,
    image_gallery_html,
    rich,
    split_text,
)
from bots.telegram.card.ui.selectors import ordered_mapping_items
from bots.telegram.card.views.titles import _titles_table_html, format_titles
from core.canonicalization import display_person_name, localize_role_token
from core.models import AggregatedAnime
from localization import DEFAULT_LOCALE, text


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


def screenshot_urls(anime: AggregatedAnime, source: str | None = None) -> list[str]:
    if source is not None:
        return dedupe_strings(anime.screenshots_by_source.get(source, []))
    values: list[str] = []
    for _, screenshots in ordered_mapping_items(
        anime.screenshots_by_source, anime.sources
    ):
        values.extend(screenshots)
    return dedupe_strings(values)


def format_screenshots(
    anime: AggregatedAnime, *, locale: str, source: str | None = None
) -> str:
    title_value = (
        text("card", "screenshots_title", locale=locale, source=source)
        if source
        else text("card", "screenshots", locale=locale)
    )
    urls = screenshot_urls(anime, source)
    if not urls:
        return f"{title_value}:\n{text('common', 'no_data', locale=locale)}"
    lines = [f"{title_value}:"]
    lines.extend(f"{index}. {url}" for index, url in enumerate(urls, start=1))
    return "\n".join(lines)


def screenshots_rich_html(
    anime: AggregatedAnime, *, locale: str, source: str | None = None
) -> str:
    title_value = (
        text("card", "screenshots_title", locale=locale, source=source)
        if source
        else text("card", "screenshots", locale=locale)
    )
    urls = screenshot_urls(anime, source)
    if not urls:
        return (
            f"<h2>{html.escape(title_value)}</h2>"
            f"<p>{html.escape(text('common', 'no_data', locale=locale))}</p>"
        )
    return f"<h2>{html.escape(title_value)}</h2>" + image_gallery_html(urls)


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
    if section == "screenshots":
        return format_screenshots(anime, source=source, locale=locale)
    return text("common", "no_data", locale=locale)


def anime_sections(
    anime: AggregatedAnime, *, locale: str = DEFAULT_LOCALE
) -> dict[str, str]:
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
        "screenshots": format_screenshots(anime, locale=locale),
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
    if section == "screenshots":
        full_screenshots = format_screenshots(anime, locale=locale)
        if text_value.strip() == full_screenshots.strip():
            return InputRichMessage(html=screenshots_rich_html(anime, locale=locale))
    return rich(text_value)
