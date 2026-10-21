from __future__ import annotations

import logging
import secrets
from dataclasses import dataclass, field
from typing import Awaitable, Callable

from aiogram import Dispatcher, F
from aiogram.filters import Command
from aiogram.filters.command import CommandObject
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from bots.session_store import ExpiringSessionStore
from core.models import SearchCandidate, SearchPage
from localization import text
from search.registry import DEFAULT_SEARCH_PROVIDER_KEYS, get_search_provider_map
from services.search import SearchService
from services.user_settings import get_user_locale

SEARCH_PAGE_SIZE = 10
MAX_SEARCH_SESSIONS = 200

PROVIDERS = get_search_provider_map()
ALL_PROVIDER_KEYS = tuple(PROVIDERS)

PROVIDER_ALIASES = {
    "mal": "mal",
    "myanimelist": "mal",
    "my-anime-list": "mal",
    "shikimori": "shikimori",
    "shiki": "shikimori",
    "шикимори": "shikimori",
    "anilist": "anilist",
    "ani": "anilist",
}

SCOPE_ALIASES = {
    "default": DEFAULT_SEARCH_PROVIDER_KEYS,
    "main": DEFAULT_SEARCH_PROVIDER_KEYS,
    "основной": DEFAULT_SEARCH_PROVIDER_KEYS,
    "all": ALL_PROVIDER_KEYS,
    "все": ALL_PROVIDER_KEYS,
}

SCOPE_CALLBACKS = {
    "default": DEFAULT_SEARCH_PROVIDER_KEYS,
    "all": ALL_PROVIDER_KEYS,
    "mal": ("mal",),
    "shikimori": ("shikimori",),
    "anilist": ("anilist",),
}


@dataclass(slots=True)
class SearchSession:
    query: str
    owner_user_id: int = 0
    provider_keys: tuple[str, ...] = ()
    pages: dict[int, SearchPage] = field(default_factory=dict)
    show_scope_label: bool = True


SESSIONS: ExpiringSessionStore[SearchSession] = ExpiringSessionStore(
    max_entries=MAX_SEARCH_SESSIONS,
)
SERVICES: dict[tuple[str, ...], SearchService] = {}


def _normalize_provider_keys(keys: tuple[str, ...] | list[str]) -> tuple[str, ...]:
    requested = set(keys)
    return tuple(key for key in ALL_PROVIDER_KEYS if key in requested)


def _service_for(
    provider_keys: tuple[str, ...],
    default_service: SearchService,
) -> SearchService:
    provider_keys = _normalize_provider_keys(provider_keys)
    if provider_keys == DEFAULT_SEARCH_PROVIDER_KEYS:
        return default_service

    service = SERVICES.get(provider_keys)
    if service is None:
        if not provider_keys:
            raise ValueError("No search providers selected")
        service = SearchService(tuple(PROVIDERS[key] for key in provider_keys))
        SERVICES[provider_keys] = service
    return service


def _scope_label(provider_keys: tuple[str, ...]) -> str:
    return " + ".join(PROVIDERS[key].name for key in provider_keys)


def _parse_scope(value: str) -> tuple[str, ...] | None:
    value = value.strip().casefold()
    if value in SCOPE_ALIASES:
        return _normalize_provider_keys(SCOPE_ALIASES[value])

    parts = [part.strip() for part in value.replace("+", ",").split(",") if part.strip()]
    if not parts:
        return None

    keys: list[str] = []
    for part in parts:
        key = PROVIDER_ALIASES.get(part)
        if key is None:
            return None
        keys.append(key)
    return _normalize_provider_keys(keys)


def _remember(
    query: str,
    owner_user_id: int,
    provider_keys: tuple[str, ...] = (),
    *,
    show_scope_label: bool = True,
) -> str:
    token = secrets.token_urlsafe(6)
    SESSIONS[token] = SearchSession(
        query=query,
        owner_user_id=int(owner_user_id),
        provider_keys=provider_keys,
        show_scope_label=show_scope_label,
    )
    return token


def _scope_keyboard(token: str, locale: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=text("search", "default_scope", locale=locale),
                    callback_data=f"xs:{token}:default",
                )
            ],
            [
                InlineKeyboardButton(text="MAL", callback_data=f"xs:{token}:mal"),
                InlineKeyboardButton(
                    text="Shikimori",
                    callback_data=f"xs:{token}:shikimori",
                ),
                InlineKeyboardButton(
                    text="AniList",
                    callback_data=f"xs:{token}:anilist",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=text("search", "all_scope", locale=locale),
                    callback_data=f"xs:{token}:all",
                )
            ],
        ]
    )


def _candidate_button_text(candidate: SearchCandidate) -> str:
    value = f"{candidate.title} ({candidate.year})" if candidate.year else candidate.title
    mal_id = candidate.external_ids.get("mal")
    if mal_id:
        value += f" · MAL {mal_id}"
    return value if len(value) <= 64 else value[:61] + "..."


def _results_keyboard(page: SearchPage, token: str, locale: str) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=_candidate_button_text(candidate),
                callback_data=f"xk:{token}:{page.page}:{index}",
            )
        ]
        for index, candidate in enumerate(page.items)
    ]

    nav: list[InlineKeyboardButton] = []
    if page.page > 1:
        nav.append(
            InlineKeyboardButton(
                text="◀️",
                callback_data=f"xp:{token}:{page.page - 1}",
            )
        )
    nav.append(
        InlineKeyboardButton(
            text=text("search", "page", locale=locale, page=page.page),
            callback_data="noop",
        )
    )
    if page.has_next:
        nav.append(
            InlineKeyboardButton(
                text="▶️",
                callback_data=f"xp:{token}:{page.page + 1}",
            )
        )
    rows.append(nav)
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _result_text(session: SearchSession, page: SearchPage, locale: str = "ru") -> str:
    if session.show_scope_label:
        value = text(
            "search",
            "scoped_results",
            locale=locale,
            scope=_scope_label(session.provider_keys),
            query=session.query,
        )
        unavailable_label = text("search", "unavailable", locale=locale)
    else:
        value = text("search", "results", locale=locale, query=session.query)
        unavailable_label = text("search", "unavailable_providers", locale=locale)

    if page.errors:
        value += f"\n\n{unavailable_label}: " + ", ".join(page.errors)
    return value


async def _load_page(
    session: SearchSession,
    page_number: int,
    default_service: SearchService,
) -> SearchPage:
    page_number = max(1, int(page_number))
    if page_number not in session.pages:
        service = _service_for(session.provider_keys, default_service)
        session.pages[page_number] = await service.search(
            session.query,
            page=page_number,
            page_size=SEARCH_PAGE_SIZE,
        )
    return session.pages[page_number]


async def _show_results(
    message: Message,
    token: str,
    session: SearchSession,
    default_service: SearchService,
    aggregate_callback: Callable[[Message, SearchCandidate, int], Awaitable[None]],
    *,
    edit: bool,
) -> None:
    locale = get_user_locale(session.owner_user_id)
    try:
        page = await _load_page(session, 1, default_service)
    except Exception as exc:
        logging.error(
            "Search failed (%s): %s: %s",
            _scope_label(session.provider_keys),
            type(exc).__name__,
            exc,
            exc_info=True,
        )
        value = text(
            "search",
            "failed_scoped" if session.show_scope_label else "failed",
            locale=locale,
        )
        if edit:
            await message.edit_text(value)
        else:
            await message.answer(value)
        return

    if not page.items:
        if page.errors:
            key = "nothing_unavailable" if session.show_scope_label else "no_results_unavailable"
            value = text(
                "search",
                key,
                locale=locale,
                sources=", ".join(page.errors),
            )
        else:
            value = text(
                "search",
                "nothing_scoped" if session.show_scope_label else "nothing",
                locale=locale,
            )
        if edit:
            await message.edit_text(value)
        else:
            await message.answer(value)
        return

    if len(page.items) == 1 and not page.has_next:
        if edit:
            try:
                await message.edit_reply_markup(reply_markup=None)
            except Exception:
                logging.debug("Could not clear single-result search keyboard", exc_info=True)
        await aggregate_callback(message, page.items[0], session.owner_user_id)
        return

    value = _result_text(session, page, locale)
    keyboard = _results_keyboard(page, token, locale)
    if edit:
        await message.edit_text(value, reply_markup=keyboard)
    else:
        await message.answer(value, reply_markup=keyboard)


def register_search_handlers(
    dp: Dispatcher,
    *,
    aggregate_callback: Callable[[Message, SearchCandidate, int], Awaitable[None]],
    default_service: SearchService,
) -> None:
    """Register both /anime and legacy /search on one shared search flow."""

    @dp.message(Command("anime"))
    async def anime_handler(message: Message, command: CommandObject) -> None:
        user_id = message.from_user.id if message.from_user else 0
        locale = get_user_locale(user_id)
        query = (command.args or "").strip()
        if not query:
            await message.answer(text("search", "anime_usage", locale=locale))
            return

        token = _remember(
            query,
            user_id,
            DEFAULT_SEARCH_PROVIDER_KEYS,
            show_scope_label=False,
        )
        await _show_results(
            message,
            token,
            SESSIONS[token],
            default_service,
            aggregate_callback,
            edit=False,
        )

    @dp.message(Command("search"))
    async def search_handler(message: Message, command: CommandObject) -> None:
        user_id = message.from_user.id if message.from_user else 0
        locale = get_user_locale(user_id)
        args = (command.args or "").strip()
        if not args:
            await message.answer(text("search", "search_usage", locale=locale))
            return

        first, separator, rest = args.partition(" ")
        parsed_scope = _parse_scope(first)

        if parsed_scope is not None and separator and rest.strip():
            query = rest.strip()
            token = _remember(query, user_id, parsed_scope)
            await _show_results(
                message,
                token,
                SESSIONS[token],
                default_service,
                aggregate_callback,
                edit=False,
            )
            return

        query = args
        token = _remember(query, user_id)
        await message.answer(
            text("search", "where", locale=locale, query=query),
            reply_markup=_scope_keyboard(token, locale),
        )

    @dp.callback_query(F.data.startswith("xs:"))
    async def search_scope_callback(callback: CallbackQuery) -> None:
        locale = get_user_locale(callback.from_user.id)
        data = (callback.data or "").split(":")
        if len(data) != 3:
            await callback.answer(text("search", "invalid_provider", locale=locale), show_alert=True)
            return

        _, token, scope_name = data
        session = SESSIONS.get(token)
        provider_keys = SCOPE_CALLBACKS.get(scope_name)
        if session is None or provider_keys is None:
            await callback.answer(text("search", "expired", locale=locale), show_alert=True)
            return
        if session.owner_user_id != callback.from_user.id:
            await callback.answer(text("card", "not_owner", locale=locale), show_alert=True)
            return
        if callback.message is None:
            await callback.answer()
            return

        session.provider_keys = _normalize_provider_keys(provider_keys)
        session.pages.clear()
        await callback.answer()
        await _show_results(
            callback.message,
            token,
            session,
            default_service,
            aggregate_callback,
            edit=True,
        )

    @dp.callback_query(F.data.startswith("xp:"))
    async def search_page_callback(callback: CallbackQuery) -> None:
        locale = get_user_locale(callback.from_user.id)
        data = (callback.data or "").split(":")
        if len(data) != 3 or not data[2].isdigit():
            await callback.answer(text("search", "invalid_page", locale=locale), show_alert=True)
            return

        _, token, page_text = data
        session = SESSIONS.get(token)
        if session is None or not session.provider_keys:
            await callback.answer(text("search", "expired", locale=locale), show_alert=True)
            return
        if session.owner_user_id != callback.from_user.id:
            await callback.answer(text("card", "not_owner", locale=locale), show_alert=True)
            return
        if callback.message is None:
            await callback.answer()
            return

        try:
            page = await _load_page(session, int(page_text), default_service)
        except Exception:
            logging.exception("Search page failed")
            await callback.answer(text("search", "load_page_failed", locale=locale), show_alert=True)
            return

        if not page.items:
            await callback.answer(text("search", "no_more", locale=locale), show_alert=True)
            return

        await callback.answer()
        await callback.message.edit_text(
            _result_text(session, page, locale),
            reply_markup=_results_keyboard(page, token, locale),
        )

    @dp.callback_query(F.data.startswith("xk:"))
    async def search_pick_callback(callback: CallbackQuery) -> None:
        locale = get_user_locale(callback.from_user.id)
        data = (callback.data or "").split(":")
        if len(data) != 4 or not data[2].isdigit() or not data[3].isdigit():
            await callback.answer(text("search", "invalid_result", locale=locale), show_alert=True)
            return

        _, token, page_text, index_text = data
        session = SESSIONS.get(token)
        if session is None or not session.provider_keys:
            await callback.answer(text("search", "expired", locale=locale), show_alert=True)
            return
        if session.owner_user_id != callback.from_user.id:
            await callback.answer(text("card", "not_owner", locale=locale), show_alert=True)
            return
        if callback.message is None:
            await callback.answer()
            return

        try:
            page = await _load_page(session, int(page_text), default_service)
        except Exception:
            logging.exception("Could not reload search page")
            await callback.answer(text("search", "get_result_failed", locale=locale), show_alert=True)
            return

        index = int(index_text)
        if index < 0 or index >= len(page.items):
            await callback.answer(text("search", "result_unavailable", locale=locale), show_alert=True)
            return

        candidate = page.items[index]
        await callback.answer()
        try:
            await callback.message.edit_reply_markup(reply_markup=None)
        except Exception:
            logging.debug("Could not remove search keyboard", exc_info=True)
        await aggregate_callback(callback.message, candidate, session.owner_user_id)
