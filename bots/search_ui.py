from __future__ import annotations

import logging
import secrets
from dataclasses import dataclass, field
from typing import Awaitable, Callable

from aiogram import Dispatcher, F
from aiogram.filters import Command
from aiogram.filters.command import CommandObject
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from core.models import SearchCandidate, SearchPage
from search.registry import DEFAULT_SEARCH_PROVIDER_KEYS, get_search_provider_map
from services.search import SearchService

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
    provider_keys: tuple[str, ...] = ()
    pages: dict[int, SearchPage] = field(default_factory=dict)


SESSIONS: dict[str, SearchSession] = {}
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


def _remember(query: str, provider_keys: tuple[str, ...] = ()) -> str:
    token = secrets.token_urlsafe(6)
    SESSIONS[token] = SearchSession(query=query, provider_keys=provider_keys)
    while len(SESSIONS) > MAX_SEARCH_SESSIONS:
        SESSIONS.pop(next(iter(SESSIONS)), None)
    return token


def _scope_keyboard(token: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Основной: Shikimori + MAL",
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
                    text="Все поисковики",
                    callback_data=f"xs:{token}:all",
                )
            ],
        ]
    )


def _candidate_button_text(candidate: SearchCandidate) -> str:
    text = f"{candidate.title} ({candidate.year})" if candidate.year else candidate.title
    mal_id = candidate.external_ids.get("mal")
    if mal_id:
        text += f" · MAL {mal_id}"
    return text if len(text) <= 64 else text[:61] + "..."


def _results_keyboard(page: SearchPage, token: str) -> InlineKeyboardMarkup:
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
            text=f"Стр. {page.page}",
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


def _result_text(session: SearchSession, page: SearchPage) -> str:
    scope = _scope_label(session.provider_keys)
    text = (
        f"Поиск только через: {scope}\n"
        f"Запрос: «{session.query}»\n\n"
        "Выбери нужное аниме:"
    )
    if page.errors:
        text += "\n\nНедоступны: " + ", ".join(page.errors)
    return text


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
    aggregate_callback: Callable[[Message, SearchCandidate], Awaitable[None]],
    *,
    edit: bool,
) -> None:
    try:
        page = await _load_page(session, 1, default_service)
    except Exception as exc:
        logging.error(
            "Explicit search failed (%s): %s: %s",
            _scope_label(session.provider_keys),
            type(exc).__name__,
            exc,
            exc_info=True,
        )
        text = "Не удалось выполнить поиск через выбранные поисковики."
        if edit:
            await message.edit_text(text)
        else:
            await message.answer(text)
        return

    if not page.items:
        if page.errors:
            text = "Ничего не найдено. Недоступны: " + ", ".join(page.errors)
        else:
            text = "Ничего не найдено через выбранные поисковики."
        if edit:
            await message.edit_text(text)
        else:
            await message.answer(text)
        return

    if len(page.items) == 1 and not page.has_next:
        if edit:
            try:
                await message.edit_reply_markup(reply_markup=None)
            except Exception:
                pass
        await aggregate_callback(message, page.items[0])
        return

    text = _result_text(session, page)
    keyboard = _results_keyboard(page, token)
    if edit:
        await message.edit_text(text, reply_markup=keyboard)
    else:
        await message.answer(text, reply_markup=keyboard)


def register_search_handlers(
    dp: Dispatcher,
    *,
    aggregate_callback: Callable[[Message, SearchCandidate], Awaitable[None]],
    default_service: SearchService,
) -> None:
    """Register /search and its callbacks on an existing dispatcher."""

    @dp.message(Command("search"))
    async def search_handler(message: Message, command: CommandObject) -> None:
        args = (command.args or "").strip()
        if not args:
            await message.answer(
                "Использование:\n"
                "/search <название> — выбрать поисковик кнопкой\n"
                "/search mal <название>\n"
                "/search shikimori <название>\n"
                "/search anilist <название>\n"
                "/search all <название>\n"
                "/search mal,shikimori <название>"
            )
            return

        first, separator, rest = args.partition(" ")
        parsed_scope = _parse_scope(first)

        if parsed_scope is not None and separator and rest.strip():
            query = rest.strip()
            token = _remember(query, parsed_scope)
            session = SESSIONS[token]
            await _show_results(
                message,
                token,
                session,
                default_service,
                aggregate_callback,
                edit=False,
            )
            return

        query = args
        token = _remember(query)
        await message.answer(
            f"Где искать «{query}»?",
            reply_markup=_scope_keyboard(token),
        )

    @dp.callback_query(F.data.startswith("xs:"))
    async def search_scope_callback(callback: CallbackQuery) -> None:
        data = (callback.data or "").split(":")
        if len(data) != 3:
            await callback.answer("Некорректный поисковик.", show_alert=True)
            return

        _, token, scope_name = data
        session = SESSIONS.get(token)
        provider_keys = SCOPE_CALLBACKS.get(scope_name)
        if session is None or provider_keys is None:
            await callback.answer("Этот поиск устарел.", show_alert=True)
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
    async def explicit_search_page_callback(callback: CallbackQuery) -> None:
        data = (callback.data or "").split(":")
        if len(data) != 3 or not data[2].isdigit():
            await callback.answer("Некорректная страница.", show_alert=True)
            return

        _, token, page_text = data
        session = SESSIONS.get(token)
        if session is None or not session.provider_keys:
            await callback.answer("Этот поиск устарел.", show_alert=True)
            return
        if callback.message is None:
            await callback.answer()
            return

        try:
            page = await _load_page(session, int(page_text), default_service)
        except Exception:
            logging.exception("Explicit search page failed")
            await callback.answer("Не удалось загрузить страницу.", show_alert=True)
            return

        if not page.items:
            await callback.answer("Больше результатов нет.", show_alert=True)
            return

        await callback.answer()
        await callback.message.edit_text(
            _result_text(session, page),
            reply_markup=_results_keyboard(page, token),
        )

    @dp.callback_query(F.data.startswith("xk:"))
    async def explicit_search_pick_callback(callback: CallbackQuery) -> None:
        data = (callback.data or "").split(":")
        if len(data) != 4 or not data[2].isdigit() or not data[3].isdigit():
            await callback.answer("Некорректный результат.", show_alert=True)
            return

        _, token, page_text, index_text = data
        session = SESSIONS.get(token)
        if session is None or not session.provider_keys:
            await callback.answer("Этот поиск устарел.", show_alert=True)
            return
        if callback.message is None:
            await callback.answer()
            return

        try:
            page = await _load_page(session, int(page_text), default_service)
        except Exception:
            logging.exception("Could not reload explicit search page")
            await callback.answer("Не удалось получить результат.", show_alert=True)
            return

        index = int(index_text)
        if index < 0 or index >= len(page.items):
            await callback.answer("Результат больше недоступен.", show_alert=True)
            return

        candidate = page.items[index]
        await callback.answer()
        try:
            await callback.message.edit_reply_markup(reply_markup=None)
        except Exception:
            logging.debug("Could not remove explicit search keyboard", exc_info=True)
        await aggregate_callback(callback.message, candidate)
