from __future__ import annotations

import asyncio
import logging

from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from bots.telegram.callbacks import (
    SectionSourceCallback,
    ViewCallback,
    resolve_key_or_legacy_index,
)
from bots.telegram.card.views.renderer import edit_standard_text
from bots.telegram.card.ui.selectors import source_options
from bots.telegram.card.runtime.state import TelegramCardState
from bots.telegram.people.loading import (
    PeopleLoadProgress as _PeopleLoadProgress,
)
from bots.telegram.people.loading import (
    SourceLoadProgress as _SourceLoadProgress,
)
from bots.telegram.people.loading import (
    ensure_lazy_people as _ensure_lazy_people,
)
from bots.telegram.people.loading import (
    progress_key as _progress_key,
)
from bots.telegram.people.loading import (
    scope_has_more as _scope_has_more,
)
from bots.telegram.people.loading import (
    scope_has_running as _scope_has_running,
)
from bots.telegram.people.loading import (
    settle_started_batches as _settle_started_batches,
)
from bots.telegram.people.loading import (
    scope_total_hint as _scope_total_hint,
)
from bots.telegram.people.loading import (
    source_names as _source_names,
)
from bots.telegram.people.views import (
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
from services.users.settings import get_user_locale


_BACKGROUND_PEOPLE_REFRESH_TASKS: set[asyncio.Task[None]] = set()


def _track_background_refresh(task: asyncio.Task[None]) -> None:
    _BACKGROUND_PEOPLE_REFRESH_TASKS.add(task)
    task.add_done_callback(_BACKGROUND_PEOPLE_REFRESH_TASKS.discard)


async def _render_people_view(
    state: TelegramCardState,
    message: Message,
    token: str,
    anime: AggregatedAnime,
    section: str,
    source_key: str | None,
    page: int,
    progress: _PeopleLoadProgress,
    *,
    locale: str,
    initial_loading: bool,
) -> None:
    sources = _source_names(anime, section, progress)
    source: str | None = None
    if source_key is not None:
        options = source_options(sources)
        source_key = resolve_key_or_legacy_index(
            source_key, [key for key, _ in options]
        )
        source = dict(options)[source_key]

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
        source_key,
        page,
        shown,
        total,
        max_page,
        locale=locale,
        source_names=sources,
        has_more=_scope_has_more(progress, source),
        initial_loading=initial_loading,
        first_page=first_page,
    )

    try:
        await message.edit_text(
            rich_message=_rich(text_value, urls), reply_markup=keyboard
        )
    except Exception:
        logging.exception(
            "Rich portrait view edit failed; falling back to standard text edit"
        )
        await edit_standard_text(
            message,
            text_value,
            reply_markup=keyboard,
            locale=locale,
        )


async def _refresh_people_after_initial_batches(
    state: TelegramCardState,
    message: Message,
    token: str,
    anime: AggregatedAnime,
    section: str,
    source_key: str | None,
    page: int,
    progress: _PeopleLoadProgress,
    revision: int,
    *,
    locale: str,
) -> None:
    try:
        await _settle_started_batches(progress, None)
        current = state.people_loads.get(_progress_key(token, section))
        if current is not progress or progress.view_revision != revision:
            return
        await _render_people_view(
            state,
            message,
            token,
            anime,
            section,
            source_key,
            page,
            progress,
            locale=locale,
            initial_loading=False,
        )
    except asyncio.CancelledError:
        raise
    except Exception:
        logging.exception("Could not refresh people view after initial batches")


async def _edit_people_view(
    state: TelegramCardState,
    message: Message,
    token: str,
    anime: AggregatedAnime,
    section: str,
    source_key: str | None,
    page: int,
    *,
    locale: str,
) -> None:
    key = _progress_key(token, section)
    existing_progress = state.people_loads.get(key)
    existing_sources = _source_names(anime, section, existing_progress)

    source: str | None = None
    if source_key is not None:
        existing_options = source_options(existing_sources)
        resolved_key = resolve_key_or_legacy_index(
            source_key, [key for key, _ in existing_options]
        )
        source = dict(existing_options)[resolved_key]
        source_key = resolved_key

    progress = await _ensure_lazy_people(
        state,
        token,
        anime,
        message,
        section,
        locale=locale,
        source=source,
        requested_page=int(page),
    )
    progress.view_revision += 1
    revision = progress.view_revision
    initial_loading = existing_progress is None and _scope_has_running(progress, None)

    await _render_people_view(
        state,
        message,
        token,
        anime,
        section,
        source_key,
        page,
        progress,
        locale=locale,
        initial_loading=initial_loading,
    )

    if initial_loading:
        _track_background_refresh(
            asyncio.create_task(
                _refresh_people_after_initial_batches(
                    state,
                    message,
                    token,
                    anime,
                    section,
                    source_key,
                    page,
                    progress,
                    revision,
                    locale=locale,
                )
            )
        )


def _parse_people_callback(raw: str) -> tuple[str, str, str | None, int] | None:
    view = ViewCallback.parse(raw)
    if view is not None and view.section in PEOPLE_SECTIONS:
        return view.token, view.section, None, view.page
    source = SectionSourceCallback.parse(raw)
    if source is not None and source.section in PEOPLE_SECTIONS:
        return source.token, source.section, source.source_key, source.page
    return None


async def handle_people_callback(
    callback: CallbackQuery, state: TelegramCardState
) -> bool:
    """Handle staff/voice callback namespaces before core card handlers."""
    parsed = _parse_people_callback(callback.data or "")
    if parsed is None:
        return False
    token, section, source_key, page = parsed

    locale = get_user_locale(callback.from_user.id)
    session = state.anime_sessions.get(token)
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
            state,
            callback.message,
            token,
            session.anime,
            section,
            source_key=source_key,
            page=page,
            locale=locale,
        )
    except ValueError:
        logging.debug("People callback source is no longer available", exc_info=True)
        try:
            await callback.message.edit_text(
                text=text("people", "source_unavailable", locale=locale),
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[
                        [
                            InlineKeyboardButton(
                                text=text("common", "back", locale=locale),
                                callback_data=ViewCallback(token, "main", 0).encode(),
                            )
                        ]
                    ]
                ),
            )
        except Exception:
            logging.exception("Could not render stale people callback fallback")
    return True


__all__ = [
    "_PeopleLoadProgress",
    "_SourceLoadProgress",
    "_edit_people_view",
    "_ensure_lazy_people",
    "_first_people_page",
    "_keyboard",
    "_page_text",
    "_sources_with_portraits",
    "handle_people_callback",
]
