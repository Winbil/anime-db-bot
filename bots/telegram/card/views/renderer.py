from __future__ import annotations

import logging

from aiogram.types import InlineKeyboardMarkup, InputRichMessage, Message

from bots.telegram.callbacks import resolve_key_or_legacy_index
from bots.telegram.card.ui.constants import RICH_MESSAGE_LIMIT, STANDARD_MESSAGE_LIMIT
from bots.telegram.card.ui.keyboards import (
    description_keyboard,
    fallback_main_keyboard,
    navigation_keyboard,
    source_section_keyboard,
)
from bots.telegram.card.views.main import display_anime_title, main_rich
from bots.telegram.card.views.popularity import (
    _popularity_tables_html,
    format_popularity,
)
from bots.telegram.card.views.rendering import (
    append_block,
    dedupe_strings,
    format_number,
    image_gallery_html,
    plain_text_to_rich_html,
    poster_html,
    rich,
    split_text as _split_text,
)
from bots.telegram.card.views.sections import (
    anime_sections,
    format_people,
    format_screenshots,
    rich_view,
    screenshot_urls,
    screenshots_rich_html,
    source_section_text,
    view_pages,
)
from bots.telegram.card.ui.selectors import (
    description_source_options,
    source_section_options,
)
from bots.telegram.card.views.titles import _titles_table_html, format_titles
from core.models import AggregatedAnime
from localization import DEFAULT_LOCALE, text

__all__ = [
    "anime_sections",
    "append_block",
    "dedupe_strings",
    "display_anime_title",
    "edit_anime_view",
    "edit_description_view",
    "edit_source_section_view",
    "edit_standard_text",
    "format_number",
    "format_people",
    "format_popularity",
    "format_screenshots",
    "format_titles",
    "image_gallery_html",
    "main_rich",
    "plain_text_to_rich_html",
    "poster_html",
    "rich",
    "rich_view",
    "screenshot_urls",
    "screenshots_rich_html",
    "send_anime_view",
    "send_standard_text",
    "source_section_text",
    "split_text",
    "view_pages",
]


def split_text(
    text_value: str, limit: int, *, locale: str = DEFAULT_LOCALE
) -> list[str]:
    return _split_text(text_value, limit, locale=locale)


async def edit_standard_text(
    message: Message,
    text_value: str,
    reply_markup: InlineKeyboardMarkup | None = None,
    *,
    locale: str = DEFAULT_LOCALE,
    limit: int = STANDARD_MESSAGE_LIMIT,
) -> None:
    """Edit callback text without discarding overflow chunks."""
    chunks = split_text(text_value, limit, locale=locale)
    await message.edit_text(text=chunks[0], reply_markup=reply_markup)
    for chunk in chunks[1:]:
        await message.answer(chunk)


async def send_standard_text(
    message: Message,
    text_value: str,
    reply_markup: InlineKeyboardMarkup | None = None,
    *,
    locale: str = DEFAULT_LOCALE,
) -> None:
    chunks = split_text(text_value, STANDARD_MESSAGE_LIMIT, locale=locale)
    for index, chunk in enumerate(chunks):
        await message.answer(
            chunk,
            reply_markup=reply_markup if index == len(chunks) - 1 else None,
        )


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
    elif section == "screenshots" and len(pages) == 1:
        rich_message = InputRichMessage(
            html=screenshots_rich_html(anime, source=source, locale=locale)
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
