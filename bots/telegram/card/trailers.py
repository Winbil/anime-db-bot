from __future__ import annotations

import logging

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, InputRichMessage, Message

from bots.telegram.card.renderer import edit_standard_text, plain_text_to_rich_html
from bots.telegram.card.service import TRAILER_SERVICE
from bots.telegram.card.state import AnimeCardSession
from core.models import TrailerRecord
from localization import text

TRAILERS_PER_PAGE = 5


def _source_names(session: AnimeCardSession) -> list[str]:
    return list(session.trailers_by_source)


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
    sources: list[str],
    *,
    selected_source_index: int | None = None,
) -> list[list[InlineKeyboardButton]]:
    buttons = [
        InlineKeyboardButton(
            text=("✓ " + source) if selected_source_index == index else source,
            callback_data=f"at:{token}:{index}:0",
        )
        for index, source in enumerate(sources)
    ]
    return [buttons[index:index + 2] for index in range(0, len(buttons), 2)]


def _chooser_keyboard(
    token: str,
    sources: list[str],
    *,
    locale: str,
) -> InlineKeyboardMarkup:
    rows = _source_rows(token, sources)
    rows.append([
        InlineKeyboardButton(
            text=text("common", "back", locale=locale),
            callback_data=f"av:{token}:main:0",
        )
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _short_button_title(value: str) -> str:
    value = " ".join(value.split()).strip()
    return value if len(value) <= 48 else value[:45].rstrip() + "…"


def _source_keyboard(
    token: str,
    sources: list[str],
    source_index: int,
    items: list[TrailerRecord],
    *,
    offset: int,
    page: int,
    page_count: int,
    locale: str,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for local_index, item in enumerate(items, start=offset + 1):
        rows.append([
            InlineKeyboardButton(
                text=_short_button_title(_trailer_title(item, local_index, locale)),
                url=item.url,
            )
        ])

    if page_count > 1:
        nav: list[InlineKeyboardButton] = []
        if page > 0:
            nav.append(InlineKeyboardButton(
                text="◀️",
                callback_data=f"at:{token}:{source_index}:{page - 1}",
            ))
        nav.append(InlineKeyboardButton(
            text=f"{page + 1}/{page_count}",
            callback_data="noop",
        ))
        if page + 1 < page_count:
            nav.append(InlineKeyboardButton(
                text="▶️",
                callback_data=f"at:{token}:{source_index}:{page + 1}",
            ))
        rows.append(nav)

    rows.append([
        InlineKeyboardButton(
            text=text("common", "sources", locale=locale),
            callback_data=f"av:{token}:trailers:0",
        ),
        InlineKeyboardButton(
            text=text("common", "back", locale=locale),
            callback_data=f"av:{token}:main:0",
        ),
    ])
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

    result = await TRAILER_SERVICE.load(session.anime.identity)
    session.trailers_by_source = result.by_source
    session.trailer_errors = result.errors
    session.trailers_loaded = True


async def edit_trailers_view(
    message: Message,
    token: str,
    session: AnimeCardSession,
    *,
    source_index: int | None = None,
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

    sources = _source_names(session)
    if source_index is None:
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
        if source_index < 0 or source_index >= len(sources):
            raise ValueError("Trailer source index is out of range")
        source = sources[source_index]
        all_items = session.trailers_by_source.get(source, [])
        page_count = max(1, (len(all_items) + TRAILERS_PER_PAGE - 1) // TRAILERS_PER_PAGE)
        page = max(0, min(int(page), page_count - 1))
        offset = page * TRAILERS_PER_PAGE
        items = all_items[offset:offset + TRAILERS_PER_PAGE]
        content = _trailer_text(source, items, offset=offset, locale=locale)
        keyboard = _source_keyboard(
            token,
            sources,
            source_index,
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
