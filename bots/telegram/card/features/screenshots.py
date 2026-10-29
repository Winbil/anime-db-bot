from __future__ import annotations

import html
import logging

from aiogram.types import InputRichMessage, Message

from bots.telegram.callbacks import resolve_key_or_legacy_index
from bots.telegram.card.ui.keyboards import navigation_keyboard, source_section_keyboard
from bots.telegram.card.views.renderer import edit_standard_text
from bots.telegram.card.ui.selectors import (
    ordered_mapping_items,
    source_section_options,
)
from core.models import AggregatedAnime
from localization import text

logger = logging.getLogger(__name__)

SCREENSHOTS_PER_PAGE = 8


def screenshot_urls(anime: AggregatedAnime, source: str | None = None) -> list[str]:
    if source is not None:
        values = anime.screenshots_by_source.get(source, [])
    else:
        values = []
        for _, screenshots in ordered_mapping_items(
            anime.screenshots_by_source, anime.sources
        ):
            values.extend(screenshots)

    result: list[str] = []
    seen: set[str] = set()
    for raw_value in values:
        value = str(raw_value or "").strip()
        key = value.casefold()
        if value and key not in seen:
            seen.add(key)
            result.append(value)
    return result


def screenshot_pages(
    anime: AggregatedAnime, source: str | None = None
) -> list[list[str]]:
    urls = screenshot_urls(anime, source)
    if not urls:
        return [[]]
    return [
        urls[index : index + SCREENSHOTS_PER_PAGE]
        for index in range(0, len(urls), SCREENSHOTS_PER_PAGE)
    ]


def _page(
    anime: AggregatedAnime,
    *,
    source: str | None,
    page: int,
) -> tuple[list[str], int, int]:
    pages = screenshot_pages(anime, source)
    page = max(0, min(page, len(pages) - 1))
    return pages[page], page, len(pages)


def _title(
    anime: AggregatedAnime,
    *,
    source: str | None,
    page: int,
    locale: str,
) -> tuple[str, list[str], int, int]:
    urls, page, page_count = _page(anime, source=source, page=page)
    title_value = (
        text("card", "screenshots_title", locale=locale, source=source)
        if source
        else text("card", "screenshots", locale=locale)
    )
    if page_count > 1 and urls:
        total = len(screenshot_urls(anime, source))
        start = page * SCREENSHOTS_PER_PAGE + 1
        end = start + len(urls) - 1
        title_value = f"{title_value} ({start}–{end}/{total})"
    return title_value, urls, page, page_count


def screenshot_rich_message(
    anime: AggregatedAnime,
    *,
    source: str | None = None,
    page: int = 0,
    locale: str,
) -> InputRichMessage:
    title_value, urls, _, _ = _title(anime, source=source, page=page, locale=locale)
    if not urls:
        body = f"<p>{html.escape(text('common', 'no_data', locale=locale))}</p>"
    else:
        images = "".join(f'<img src="{html.escape(url, quote=True)}"/>' for url in urls)
        body = images if len(urls) == 1 else f"<tg-slideshow>{images}</tg-slideshow>"
    return InputRichMessage(html=f"<h2>{html.escape(title_value)}</h2>{body}")


def screenshot_text(
    anime: AggregatedAnime,
    *,
    source: str | None = None,
    page: int = 0,
    locale: str,
) -> str:
    title_value, urls, page, _ = _title(anime, source=source, page=page, locale=locale)
    if not urls:
        return f"{title_value}:\n{text('common', 'no_data', locale=locale)}"
    start = page * SCREENSHOTS_PER_PAGE + 1
    lines = [f"{title_value}:"]
    lines.extend(f"{index}. {url}" for index, url in enumerate(urls, start=start))
    return "\n".join(lines)


async def edit_screenshots_view(
    message: Message,
    token: str,
    anime: AggregatedAnime,
    *,
    source_key: str | None,
    page: int,
    locale: str,
) -> None:
    source: str | None = None
    resolved_source_key: str | None = None
    if source_key is not None:
        options = source_section_options(anime, "screenshots")
        keys = [key for key, _ in options]
        resolved_source_key = resolve_key_or_legacy_index(source_key, keys)
        source = dict(options)[resolved_source_key]

    pages = screenshot_pages(anime, source)
    page = max(0, min(page, len(pages) - 1))
    if resolved_source_key is None:
        keyboard = navigation_keyboard(
            token,
            anime,
            "screenshots",
            page,
            len(pages),
            locale=locale,
        )
    else:
        keyboard = source_section_keyboard(
            token,
            anime,
            "screenshots",
            resolved_source_key,
            page,
            len(pages),
            locale=locale,
        )

    try:
        await message.edit_text(
            rich_message=screenshot_rich_message(
                anime, source=source, page=page, locale=locale
            ),
            reply_markup=keyboard,
        )
    except Exception:
        logger.exception(
            "Rich screenshot gallery edit failed; falling back to standard text edit"
        )
        await edit_standard_text(
            message,
            screenshot_text(anime, source=source, page=page, locale=locale),
            reply_markup=keyboard,
            locale=locale,
        )
