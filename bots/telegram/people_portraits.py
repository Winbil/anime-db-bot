from __future__ import annotations

import logging

from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from bots.telegram.callbacks import SectionSourceCallback, ViewCallback
from bots.telegram.card.constants import STANDARD_MESSAGE_LIMIT
from bots.telegram.card.renderer import split_text
from bots.telegram.card.state import ANIME_SESSIONS
from bots.telegram.people_loading import (
    PEOPLE_LOADS as _PEOPLE_LOADS,
    PeopleLoadProgress as _PeopleLoadProgress,
    SourceLoadProgress as _SourceLoadProgress,
    ensure_lazy_people as _ensure_lazy_people,
    progress_key as _progress_key,
    scope_has_more as _scope_has_more,
    scope_total_hint as _scope_total_hint,
    source_names as _source_names,
)
from bots.telegram.people_views import (
    PEOPLE_SECTIONS,
    _first_people_page,
    _keyboard,
    _page_text,
    _people_state,
    _rich,
    _sources_with_portraits,
)
from core.models import AggregatedAnime
from localization import text
from services.user_settings import get_user_locale


async def _edit_people_view(
    message: Message,
    token: str,
    anime: AggregatedAnime,
    section: str,
    source_index: int | None,
    page: int,
    *,
    locale: str,
) -> None:
    key = _progress_key(token, section)
    existing_progress = _PEOPLE_LOADS.get(key)
    existing_sources = _source_names(anime, section, existing_progress)

    source: str | None = None
    if source_index is not None:
        if source_index < 0 or source_index >= len(existing_sources):
            raise ValueError("Portrait source index is out of range")
        source = existing_sources[source_index]

    progress = await _ensure_lazy_people(
        token,
        anime,
        message,
        section,
        locale=locale,
        source=source,
        requested_page=int(page),
    )

    sources = _source_names(anime, section, progress)
    if source_index is not None:
        if source_index < 0 or source_index >= len(sources):
            raise ValueError("Portrait source index is out of range")
        source = sources[source_index]

    without, with_portraits = _people_state(anime, section, source)
    max_page = len(with_portraits)
    first_page = _first_people_page(without, with_portraits)
    page = max(first_page, min(int(page), max_page))
    total_hint = _scope_total_hint(anime, section, progress, source)
    text_value, urls, shown, total, page = _page_text(
        anime,
        section,
        source,
        page,
        locale=locale,
        total_hint=total_hint,
    )
    keyboard = _keyboard(
        token,
        anime,
        section,
        source_index,
        page,
        shown,
        total,
        max_page,
        locale=locale,
        source_names=sources,
        has_more=_scope_has_more(progress, source),
        first_page=first_page,
    )

    try:
        await message.edit_text(rich_message=_rich(text_value, urls), reply_markup=keyboard)
    except Exception:
        logging.exception("Rich portrait view edit failed; falling back to standard text edit")
        await message.edit_text(
            text=split_text(text_value, STANDARD_MESSAGE_LIMIT, locale=locale)[0],
            reply_markup=keyboard,
        )


def _parse_people_callback(raw: str) -> tuple[str, str, int | None, int] | None:
    view = ViewCallback.parse(raw)
    if view is not None and view.section in PEOPLE_SECTIONS:
        return view.token, view.section, None, view.page
    source = SectionSourceCallback.parse(raw)
    if source is not None and source.section in PEOPLE_SECTIONS:
        return source.token, source.section, source.source_index, source.page
    return None


async def handle_people_callback(callback: CallbackQuery) -> bool:
    """Handle staff/voice callback namespaces before core card handlers."""
    parsed = _parse_people_callback(callback.data or "")
    if parsed is None:
        return False
    token, section, source_index, page = parsed

    locale = get_user_locale(callback.from_user.id)
    session = ANIME_SESSIONS.get(token)
    if session is None:
        await callback.answer(text("card", "expired", locale=locale), show_alert=True)
        return True
    if session.owner_user_id != callback.from_user.id:
        await callback.answer(text("card", "not_owner", locale=locale), show_alert=True)
        return True
    if callback.message is None:
        await callback.answer()
        return True

    await callback.answer()
    try:
        await _edit_people_view(
            callback.message,
            token,
            session.anime,
            section,
            source_index=source_index,
            page=page,
            locale=locale,
        )
    except ValueError:
        logging.debug("People callback source is no longer available", exc_info=True)
        try:
            await callback.message.edit_text(
                text=text("people", "source_unavailable", locale=locale),
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                    InlineKeyboardButton(
                        text=text("common", "back", locale=locale),
                        callback_data=ViewCallback(token, "main", 0).encode(),
                    )
                ]]),
            )
        except Exception:
            logging.exception("Could not render stale people callback fallback")
    return True


__all__ = [
    "_PeopleLoadProgress",
    "_SourceLoadProgress",
    "_PEOPLE_LOADS",
    "_edit_people_view",
    "_ensure_lazy_people",
    "_first_people_page",
    "_keyboard",
    "_page_text",
    "_sources_with_portraits",
    "handle_people_callback",
]
