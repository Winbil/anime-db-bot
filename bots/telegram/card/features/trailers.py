from __future__ import annotations

import logging

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputRichMessage,
    Message,
)

from bots.telegram.callbacks import KeyedPageCallback, resolve_key_or_legacy_index
from bots.telegram.pagination import card_picker_callback
from bots.telegram.card.views.renderer import (
    edit_standard_text,
    plain_text_to_rich_html,
)
from bots.telegram.card.runtime.state import AnimeCardSession
from core.models import TrailerRecord
from localization import text
from services.runtime.app_context import get_app_context

TRAILERS_PER_PAGE = 5


def _source_options(session: AnimeCardSession) -> list[tuple[str, str]]:
    result: list[tuple[str, str]] = []
    seen: set[str] = set()
    for source_name, items in session.trailers_by_source.items():
        key = session.trailer_key_by_source.get(source_name)
        if not key and items:
            key = items[0].backend
        key = (key or "").strip().casefold()
        if key and key not in seen:
            seen.add(key)
            result.append((key, source_name))
    return result


def _source_name_for_selector(
    session: AnimeCardSession,
    selector: str,
) -> tuple[str, str]:
    options = _source_options(session)
    keys = [key for key, _ in options]
    key = resolve_key_or_legacy_index(selector, keys)
    return key, dict(options)[key]


def _kind_label(kind: str, locale: str) -> str:
    return text("trailer_kind", kind, locale=locale, default=kind)


def _trailer_title(item: TrailerRecord, number: int, locale: str) -> str:
    value = (item.title or "").strip()
    if value:
        return value
    return text("card", "trailer_default", locale=locale, number=number)


def _trailer_text(
    source: str,
    items: list[TrailerRecord],
    *,
    offset: int,
    locale: str,
) -> str:
    lines = [text("card", "trailers_title", locale=locale, source=source)]
    if not items:
        lines.extend(["", text("card", "trailers_empty", locale=locale)])
        return "\n".join(lines)

    for index, item in enumerate(items, start=offset + 1):
        lines.extend(["", f"{index}. {_trailer_title(item, index, locale)}"])
        lines.append(
            text(
                "card",
                "trailer_kind",
                locale=locale,
                value=_kind_label(item.kind, locale),
            )
        )
        if item.hosting:
            lines.append(
                text(
                    "card",
                    "trailer_hosting",
                    locale=locale,
                    value=item.hosting,
                )
            )
    return "\n".join(lines)


def _source_rows(
    token: str,
    sources: list[tuple[str, str]],
    *,
    selected_source_key: str | None = None,
) -> list[list[InlineKeyboardButton]]:
    buttons = [
        InlineKeyboardButton(
            text=("✓ " + source_name) if selected_source_key == key else source_name,
            callback_data=KeyedPageCallback("at", token, key, 0).encode(),
        )
        for key, source_name in sources
    ]
    return [buttons[index : index + 2] for index in range(0, len(buttons), 2)]


def _chooser_keyboard(
    token: str,
    sources: list[tuple[str, str]],
    *,
    locale: str,
) -> InlineKeyboardMarkup:
    rows = _source_rows(token, sources)
    rows.append(
        [
            InlineKeyboardButton(
                text=text("common", "back", locale=locale),
                callback_data=f"av:{token}:main:0",
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _short_button_title(value: str) -> str:
    value = " ".join(value.split()).strip()
    return value if len(value) <= 48 else value[:45].rstrip() + "…"


def _source_keyboard(
    token: str,
    sources: list[tuple[str, str]],
    source_key: str,
    items: list[TrailerRecord],
    *,
    offset: int,
    page: int,
    page_count: int,
    locale: str,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for local_index, item in enumerate(items, start=offset + 1):
        rows.append(
            [
                InlineKeyboardButton(
                    text=_short_button_title(_trailer_title(item, local_index, locale)),
                    url=item.url,
                )
            ]
        )

    if page_count > 1:
        nav: list[InlineKeyboardButton] = []
        if page > 0:
            nav.append(
                InlineKeyboardButton(
                    text="◀️",
                    callback_data=KeyedPageCallback(
                        "at", token, source_key, page - 1
                    ).encode(),
                )
            )
        nav.append(
            InlineKeyboardButton(
                text=f"{page + 1}/{page_count}",
                callback_data=card_picker_callback(
                    token, f"at~{source_key}", page, page_count
                ),
            )
        )
        if page + 1 < page_count:
            nav.append(
                InlineKeyboardButton(
                    text="▶️",
                    callback_data=KeyedPageCallback(
                        "at", token, source_key, page + 1
                    ).encode(),
                )
            )
        rows.append(nav)

    rows.append(
        [
            InlineKeyboardButton(
                text=text("common", "sources", locale=locale),
                callback_data=f"av:{token}:trailers:0",
            ),
            InlineKeyboardButton(
                text=text("common", "back", locale=locale),
                callback_data=f"av:{token}:main:0",
            ),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _ensure_loaded(
    message: Message,
    session: AnimeCardSession,
    *,
    locale: str,
) -> None:
    if session.trailers_loaded:
        return

    try:
        await message.edit_text(
            text=text("card", "trailers_loading", locale=locale),
            reply_markup=None,
        )
    except Exception:
        logging.debug("Could not show trailer loading state", exc_info=True)

    result = await get_app_context().trailer_service.load(session.anime.identity)
    session.trailers_by_source = result.by_source
    session.trailer_key_by_source = result.key_by_source
    session.trailer_errors = result.errors
    session.trailers_loaded = True


async def edit_trailers_view(
    message: Message,
    token: str,
    session: AnimeCardSession,
    *,
    source_key: str | None = None,
    page: int = 0,
    locale: str,
) -> None:
    try:
        await _ensure_loaded(message, session, locale=locale)
    except Exception:
        logging.exception("Could not load trailer sources")
        session.trailers_loaded = True
        session.trailers_by_source = {}
        session.trailer_errors = {"trailers": "load failed"}

    sources = _source_options(session)
    if source_key is None:
        if sources:
            content = text("card", "trailers_choose", locale=locale)
            if session.trailer_errors:
                content += "\n\n" + text(
                    "card",
                    "unavailable",
                    locale=locale,
                    value=", ".join(session.trailer_errors),
                )
        elif session.trailer_errors:
            content = text("card", "trailers_load_failed", locale=locale)
        else:
            content = text("card", "trailers_empty", locale=locale)
        keyboard = _chooser_keyboard(token, sources, locale=locale)
    else:
        source_key, source = _source_name_for_selector(session, source_key)
        all_items = session.trailers_by_source.get(source, [])
        page_count = max(
            1, (len(all_items) + TRAILERS_PER_PAGE - 1) // TRAILERS_PER_PAGE
        )
        page = max(0, min(int(page), page_count - 1))
        offset = page * TRAILERS_PER_PAGE
        items = all_items[offset : offset + TRAILERS_PER_PAGE]
        content = _trailer_text(source, items, offset=offset, locale=locale)
        keyboard = _source_keyboard(
            token,
            sources,
            source_key,
            items,
            offset=offset,
            page=page,
            page_count=page_count,
            locale=locale,
        )

    try:
        await message.edit_text(
            rich_message=InputRichMessage(html=plain_text_to_rich_html(content)),
            reply_markup=keyboard,
        )
    except Exception:
        logging.exception("Rich trailer view edit failed; falling back to text")
        await edit_standard_text(
            message,
            content,
            reply_markup=keyboard,
            locale=locale,
            limit=3900,
        )
