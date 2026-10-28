from __future__ import annotations

import logging
import re
import secrets
from dataclasses import dataclass, field
from typing import Awaitable, Callable

from aiogram import Dispatcher, F
from aiogram.filters import BaseFilter, Command
from aiogram.filters.command import CommandObject
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaPhoto,
    InputRichMessage,
    InputRichMessageMedia,
    Message,
)

from bots.session_store import ExpiringSessionStore
from bots.telegram.card.renderer import plain_text_to_rich_html
from core.models import SearchCandidate, SearchResultSet
from core.settings import get_settings
from core.source_names import MAL_SOURCE_NAME
from localization import text
from search.registry import DEFAULT_SEARCH_PROVIDER_KEYS, get_search_provider_map
from services.direct_lookup import DirectIdLookupService
from services.search import SearchService
from services.search_expansion import expand_text_search
from services.user_settings import get_user_locale

MAX_SEARCH_SESSIONS = 200
MAX_SCOPE_SESSIONS = 200
MAX_PENDING_INPUTS = 500


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

_SOURCE_LABELS = {
    "mal": MAL_SOURCE_NAME,
    "myanimelist": MAL_SOURCE_NAME,
    "anilist": "AniList",
    "shikimori": "Shikimori",
}

_DIRECT_ID_RE = re.compile(r"^(?:(?P<source>[a-zA-Z0-9_-]+):)?(?P<id>[0-9]+)$")

_UI = {
    "ru": {
        "choose_source": "Где искать аниме? После выбора отправь название или ID.",
        "all": "Все",
        "cancel": "Отмена",
        "waiting": "Источник выбран: {scope}. Отправь название аниме или ID следующим сообщением.\n\nОтмена: /cancel",
        "cancelled": "Поиск отменён.",
        "nothing_pending": "Нет активного пошагового поиска.",
        "expired": "Этот поиск устарел. Запусти /anime ещё раз.",
        "details": "Подробнее",
        "result": "Результат поиска",
        "year": "Год: {year}",
        "ids": "ID источников:",
        "no_ids": "ID источников не найдены.",
        "unavailable": "Недоступны: {sources}",
        "scope_mismatch": "Этот пошаговый поиск ограничен источником {scope}.",
        "failed": "Не удалось выполнить поиск. Причина записана в лог.",
    },
    "en": {
        "choose_source": "Where should I search? After choosing, send an anime title or ID.",
        "all": "All",
        "cancel": "Cancel",
        "waiting": "Selected source: {scope}. Send an anime title or ID in your next message.\n\nCancel: /cancel",
        "cancelled": "Search cancelled.",
        "nothing_pending": "There is no active step-by-step search.",
        "expired": "This search expired. Start /anime again.",
        "details": "Details",
        "result": "Search result",
        "year": "Year: {year}",
        "ids": "Source IDs:",
        "no_ids": "No source IDs found.",
        "unavailable": "Unavailable: {sources}",
        "scope_mismatch": "This step-by-step search is restricted to {scope}.",
        "failed": "Search failed. The reason was written to the log.",
    },
}


@dataclass(slots=True)
class SearchSession:
    query: str
    owner_user_id: int
    items: list[SearchCandidate] = field(default_factory=list)
    complete: bool = True
    errors: dict[str, str] = field(default_factory=dict)
    poster_file_ids: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class ScopeSelectionSession:
    owner_user_id: int
    chat_id: int


@dataclass(slots=True)
class PendingAnimeInput:
    owner_user_id: int
    chat_id: int
    provider_keys: tuple[str, ...]
    direct_source_keys: tuple[str, ...] | None
    scope_label: str


_input_ttl = max(60, get_settings().telegram.anime_input_ttl_seconds)
SESSIONS: ExpiringSessionStore[SearchSession] = ExpiringSessionStore(
    max_entries=MAX_SEARCH_SESSIONS,
)
SCOPE_SESSIONS: ExpiringSessionStore[ScopeSelectionSession] = ExpiringSessionStore(
    max_entries=MAX_SCOPE_SESSIONS,
    ttl_seconds=_input_ttl,
)
PENDING_INPUTS: ExpiringSessionStore[PendingAnimeInput] = ExpiringSessionStore(
    max_entries=MAX_PENDING_INPUTS,
    ttl_seconds=_input_ttl,
)
SERVICES: dict[tuple[str, ...], SearchService] = {}


def _ui(locale: str, key: str, **kwargs) -> str:
    language = "en" if str(locale).casefold().startswith("en") else "ru"
    value = _UI[language][key]
    return value.format(**kwargs) if kwargs else value


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
        service = SearchService(
            tuple(PROVIDERS[key] for key in provider_keys),
            settings=default_service.settings,
        )
        SERVICES[provider_keys] = service
    return service


def _source_label(key: str) -> str:
    return _SOURCE_LABELS.get(key.casefold(), key.upper())


def _scope_label(provider_keys: tuple[str, ...]) -> str:
    return " + ".join(_source_label(key) for key in provider_keys)


def _parse_scope(value: str) -> tuple[str, ...] | None:
    value = value.strip().casefold()
    if value in {"all", "все"}:
        return ALL_PROVIDER_KEYS
    if value in {"default", "main", "основной"}:
        return DEFAULT_SEARCH_PROVIDER_KEYS

    parts = [part.strip() for part in value.replace("+", ",").split(",") if part.strip()]
    if not parts:
        return None

    keys: list[str] = []
    for part in parts:
        key = PROVIDER_ALIASES.get(part, part if part in PROVIDERS else None)
        if key is None:
            return None
        keys.append(key)
    return _normalize_provider_keys(keys)


def _parse_direct_query(
    value: str,
    supported_source_keys: tuple[str, ...] | list[str],
) -> tuple[str | None, str] | None:
    match = _DIRECT_ID_RE.fullmatch((value or "").strip())
    if match is None:
        return None

    external_id = match.group("id")
    raw_source = (match.group("source") or "").casefold()
    if not raw_source:
        return None, external_id

    supported = {str(key).casefold() for key in supported_source_keys}
    source_key = PROVIDER_ALIASES.get(raw_source, raw_source)
    if source_key not in supported:
        return None
    return source_key, external_id


def _scope_keyboard(token: str, locale: str) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [[
        InlineKeyboardButton(
            text=_ui(locale, "all"),
            callback_data=f"sc:{token}:all",
        )
    ]]

    provider_buttons = [
        InlineKeyboardButton(
            text=_source_label(key),
            callback_data=f"sc:{token}:{key}",
        )
        for key in ALL_PROVIDER_KEYS
    ]
    rows.extend(
        provider_buttons[index:index + 2]
        for index in range(0, len(provider_buttons), 2)
    )
    rows.append([
        InlineKeyboardButton(
            text=_ui(locale, "cancel"),
            callback_data=f"sx:{token}",
        )
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _waiting_keyboard(token: str, locale: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text=_ui(locale, "cancel"),
            callback_data=f"sx:{token}",
        )
    ]])


def _preview_keyboard(
    token: str,
    index: int,
    total: int,
    *,
    complete: bool,
    locale: str,
) -> InlineKeyboardMarkup:
    nav: list[InlineKeyboardButton] = []
    if index > 0:
        nav.append(
            InlineKeyboardButton(text="◀️", callback_data=f"sr:{token}:{index - 1}")
        )

    suffix = "" if complete else "+"
    nav.append(
        InlineKeyboardButton(
            text=f"{index + 1}/{total}{suffix}",
            callback_data="noop",
        )
    )
    if index + 1 < total:
        nav.append(
            InlineKeyboardButton(text="▶️", callback_data=f"sr:{token}:{index + 1}")
        )

    return InlineKeyboardMarkup(inline_keyboard=[
        nav,
        [
            InlineKeyboardButton(
                text=_ui(locale, "details"),
                callback_data=f"sd:{token}:{index}",
            )
        ],
    ])


def _preview_text(
    session: SearchSession,
    candidate: SearchCandidate,
    *,
    locale: str,
) -> str:
    lines = [_ui(locale, "result"), "", candidate.title]
    if candidate.year:
        lines.append(_ui(locale, "year", year=candidate.year))

    lines.extend(["", _ui(locale, "ids")])
    if candidate.external_ids:
        preferred = ["mal", "anilist", "shikimori"]
        ordered = [key for key in preferred if key in candidate.external_ids]
        ordered.extend(sorted(set(candidate.external_ids) - set(ordered)))
        lines.extend(
            f"{_source_label(key)}: {candidate.external_ids[key]}"
            for key in ordered
        )
    else:
        lines.append(_ui(locale, "no_ids"))

    if session.errors:
        lines.extend([
            "",
            _ui(locale, "unavailable", sources=", ".join(session.errors)),
        ])
    return "\n".join(lines)


def _preview_poster_url(candidate: SearchCandidate) -> str:
    for value in candidate.posters:
        value = str(value or "").strip()
        if value:
            return value
    return ""


def _preview_rich(
    text_value: str,
    candidate: SearchCandidate,
    *,
    media_value: str | None = None,
) -> InputRichMessage:
    body = plain_text_to_rich_html(text_value)
    poster_url = _preview_poster_url(candidate)
    if not poster_url:
        return InputRichMessage(html=body)

    media_id = "cover"
    return InputRichMessage(
        html=f'<img src="tg://photo?id={media_id}"/>{body}',
        media=[
            InputRichMessageMedia(
                id=media_id,
                media=InputMediaPhoto(media=media_value or poster_url),
            )
        ],
    )


def _remember_preview_file_id(
    session: SearchSession,
    candidate: SearchCandidate,
    result: Message | bool | None,
) -> bool:
    if not isinstance(result, Message):
        return False
    poster_url = _preview_poster_url(candidate)
    if not poster_url:
        return False

    rich_message = getattr(result, "rich_message", None)
    blocks = getattr(rich_message, "blocks", None) or []
    for block in blocks:
        photos = getattr(block, "photo", None) or []
        if not photos:
            continue
        best = max(
            photos,
            key=lambda photo: (
                int(getattr(photo, "width", 0) or 0)
                * int(getattr(photo, "height", 0) or 0)
            ),
        )
        file_id = str(getattr(best, "file_id", "") or "").strip()
        if file_id:
            session.poster_file_ids[poster_url] = file_id
            return True
    return False


def _remember_results(
    query: str,
    owner_user_id: int,
    result_set: SearchResultSet,
) -> str:
    token = secrets.token_urlsafe(6)
    SESSIONS[token] = SearchSession(
        query=query,
        owner_user_id=int(owner_user_id),
        items=list(result_set.items),
        complete=result_set.complete,
        errors=dict(result_set.errors),
    )
    return token


def _remember_scope(owner_user_id: int, chat_id: int) -> str:
    token = secrets.token_urlsafe(6)
    SCOPE_SESSIONS[token] = ScopeSelectionSession(
        owner_user_id=int(owner_user_id),
        chat_id=int(chat_id),
    )
    return token


def _pending_key(user_id: int) -> str:
    return str(int(user_id))


class PendingAnimeInputFilter(BaseFilter):
    """Match only the next text from the owner/chat of a live /anime flow."""

    async def __call__(self, message: Message) -> bool:
        if message.from_user is None or not message.text or message.text.startswith("/"):
            return False
        pending = PENDING_INPUTS.get(_pending_key(message.from_user.id))
        return pending is not None and pending.chat_id == message.chat.id


def _clear_pending(user_id: int) -> bool:
    key = _pending_key(user_id)
    if PENDING_INPUTS.get(key) is None:
        return False
    try:
        del PENDING_INPUTS[key]
    except KeyError:
        return False
    return True


async def _send_preview(
    message: Message,
    token: str,
    session: SearchSession,
    index: int,
    *,
    edit: bool,
) -> None:
    locale = get_user_locale(session.owner_user_id)
    if not session.items:
        value = text("search", "nothing", locale=locale)
        if session.errors:
            value = text(
                "search",
                "no_results_unavailable",
                locale=locale,
                sources=", ".join(session.errors),
            )
        if edit:
            await message.edit_text(value, reply_markup=None)
        else:
            await message.answer(value)
        return

    index = max(0, min(index, len(session.items) - 1))
    candidate = session.items[index]
    text_value = _preview_text(session, candidate, locale=locale)
    keyboard = _preview_keyboard(
        token,
        index,
        len(session.items),
        complete=session.complete,
        locale=locale,
    )
    poster_url = _preview_poster_url(candidate)

    # Telegram occasionally accepts a newly sent rich message but renders its
    # remote image as text-only. The edit path is reliable in the same clients,
    # so page 1 is bootstrapped as a normal message and immediately upgraded in
    # place. Pagination itself remains a single edit per click.
    if not edit:
        sent_message = await message.answer(text_value, reply_markup=keyboard)
        if not poster_url:
            return
        try:
            result = await sent_message.edit_text(
                rich_message=_preview_rich(
                    text_value,
                    candidate,
                    media_value=poster_url,
                ),
                reply_markup=keyboard,
            )
            _remember_preview_file_id(session, candidate, result)
        except Exception:
            logging.debug(
                "Initial rich search preview upgrade failed; keeping plain text",
                exc_info=True,
            )
        return

    cached_file_id = session.poster_file_ids.get(poster_url) if poster_url else None

    async def edit_rich(media_value: str | None) -> Message | bool:
        return await message.edit_text(
            rich_message=_preview_rich(
                text_value,
                candidate,
                media_value=media_value,
            ),
            reply_markup=keyboard,
        )

    try:
        result = await edit_rich(cached_file_id)
        _remember_preview_file_id(session, candidate, result)
        return
    except Exception:
        if cached_file_id and poster_url:
            session.poster_file_ids.pop(poster_url, None)
            logging.debug(
                "Cached Telegram search cover failed; retrying source URL",
                exc_info=True,
            )
            try:
                result = await edit_rich(poster_url)
                _remember_preview_file_id(session, candidate, result)
                return
            except Exception:
                logging.debug(
                    "Rich search preview retry failed; using plain text",
                    exc_info=True,
                )
        else:
            logging.debug("Rich search preview failed; using plain text", exc_info=True)

    await message.edit_text(text_value, reply_markup=keyboard)


async def _execute_query(
    message: Message,
    query: str,
    owner_user_id: int,
    *,
    provider_keys: tuple[str, ...],
    direct_source_keys: tuple[str, ...] | None,
    default_service: SearchService,
    direct_lookup: DirectIdLookupService,
) -> None:
    locale = get_user_locale(owner_user_id)
    parsed_direct = _parse_direct_query(query, direct_lookup.source_keys)

    try:
        if parsed_direct is not None:
            explicit_source, external_id = parsed_direct
            if explicit_source is not None:
                if direct_source_keys is not None and explicit_source not in direct_source_keys:
                    await message.answer(
                        _ui(
                            locale,
                            "scope_mismatch",
                            scope=_scope_label(provider_keys),
                        )
                    )
                    return
                lookup_keys: tuple[str, ...] | None = (explicit_source,)
            else:
                lookup_keys = direct_source_keys
            result_set = await direct_lookup.lookup(
                external_id,
                source_keys=lookup_keys,
            )
        else:
            service = _service_for(provider_keys, default_service)
            result_set = await service.collect(query)
            if len(provider_keys) > 1:
                result_set = await expand_text_search(
                    service=service,
                    direct_lookup=direct_lookup,
                    query=query,
                    initial=result_set,
                )
    except Exception as exc:
        logging.error(
            "Anime search failed for %r: %s: %s",
            query,
            type(exc).__name__,
            exc,
            exc_info=True,
        )
        await message.answer(_ui(locale, "failed"))
        return

    token = _remember_results(query, owner_user_id, result_set)
    await _send_preview(message, token, SESSIONS[token], 0, edit=False)


def register_search_handlers(
    dp: Dispatcher,
    *,
    aggregate_callback: Callable[[Message, SearchCandidate, int], Awaitable[None]],
    default_service: SearchService,
    direct_lookup: DirectIdLookupService,
) -> None:
    """Register the single public anime-search command and its interactive flow."""

    @dp.message(Command("anime"))
    async def anime_handler(message: Message, command: CommandObject) -> None:
        user_id = message.from_user.id if message.from_user else 0
        locale = get_user_locale(user_id)
        query = (command.args or "").strip()

        if query:
            await _execute_query(
                message,
                query,
                user_id,
                provider_keys=DEFAULT_SEARCH_PROVIDER_KEYS,
                direct_source_keys=None,
                default_service=default_service,
                direct_lookup=direct_lookup,
            )
            return

        token = _remember_scope(user_id, message.chat.id)
        await message.answer(
            _ui(locale, "choose_source"),
            reply_markup=_scope_keyboard(token, locale),
        )

    @dp.message(Command("cancel"))
    async def cancel_search_handler(message: Message) -> None:
        user_id = message.from_user.id if message.from_user else 0
        locale = get_user_locale(user_id)
        if _clear_pending(user_id):
            await message.answer(_ui(locale, "cancelled"))
        else:
            await message.answer(_ui(locale, "nothing_pending"))

    @dp.callback_query(F.data.startswith("sc:"))
    async def scope_callback(callback: CallbackQuery) -> None:
        locale = get_user_locale(callback.from_user.id)
        parts = (callback.data or "").split(":")
        if len(parts) != 3:
            await callback.answer(text("search", "invalid_provider", locale=locale), show_alert=True)
            return

        _, token, selected = parts
        scope_session = SCOPE_SESSIONS.get(token)
        if scope_session is None:
            await callback.answer(_ui(locale, "expired"), show_alert=True)
            return
        if scope_session.owner_user_id != callback.from_user.id:
            await callback.answer(text("card", "not_owner", locale=locale), show_alert=True)
            return
        if callback.message is None:
            await callback.answer()
            return

        if selected == "all":
            provider_keys = ALL_PROVIDER_KEYS
            direct_source_keys = None
            scope_label = _ui(locale, "all")
        elif selected in PROVIDERS:
            provider_keys = (selected,)
            direct_source_keys = (selected,)
            scope_label = _source_label(selected)
        else:
            await callback.answer(text("search", "invalid_provider", locale=locale), show_alert=True)
            return

        PENDING_INPUTS[_pending_key(callback.from_user.id)] = PendingAnimeInput(
            owner_user_id=callback.from_user.id,
            chat_id=scope_session.chat_id,
            provider_keys=provider_keys,
            direct_source_keys=direct_source_keys,
            scope_label=scope_label,
        )
        await callback.answer()
        await callback.message.edit_text(
            _ui(locale, "waiting", scope=scope_label),
            reply_markup=_waiting_keyboard(token, locale),
        )

    @dp.callback_query(F.data.startswith("sx:"))
    async def cancel_scope_callback(callback: CallbackQuery) -> None:
        locale = get_user_locale(callback.from_user.id)
        parts = (callback.data or "").split(":")
        if len(parts) != 2:
            await callback.answer()
            return
        _, token = parts
        scope_session = SCOPE_SESSIONS.get(token)
        if scope_session is not None and scope_session.owner_user_id != callback.from_user.id:
            await callback.answer(text("card", "not_owner", locale=locale), show_alert=True)
            return

        _clear_pending(callback.from_user.id)
        try:
            del SCOPE_SESSIONS[token]
        except KeyError:
            pass
        await callback.answer()
        if callback.message is not None:
            await callback.message.edit_text(_ui(locale, "cancelled"), reply_markup=None)

    @dp.message(PendingAnimeInputFilter())
    async def pending_anime_input_handler(message: Message) -> None:
        user_id = message.from_user.id if message.from_user else 0
        pending = PENDING_INPUTS.get(_pending_key(user_id))
        if pending is None or pending.chat_id != message.chat.id:
            return

        _clear_pending(user_id)
        query = (message.text or "").strip()
        if not query:
            return

        await _execute_query(
            message,
            query,
            user_id,
            provider_keys=pending.provider_keys,
            direct_source_keys=pending.direct_source_keys,
            default_service=default_service,
            direct_lookup=direct_lookup,
        )

    @dp.callback_query(F.data.startswith("sr:"))
    async def result_page_callback(callback: CallbackQuery) -> None:
        locale = get_user_locale(callback.from_user.id)
        parts = (callback.data or "").split(":")
        if len(parts) != 3 or not parts[2].isdigit():
            await callback.answer(text("search", "invalid_page", locale=locale), show_alert=True)
            return

        _, token, index_text = parts
        session = SESSIONS.get(token)
        if session is None:
            await callback.answer(text("search", "expired", locale=locale), show_alert=True)
            return
        if session.owner_user_id != callback.from_user.id:
            await callback.answer(text("card", "not_owner", locale=locale), show_alert=True)
            return
        if callback.message is None:
            await callback.answer()
            return

        index = int(index_text)
        if index < 0 or index >= len(session.items):
            await callback.answer(text("search", "result_unavailable", locale=locale), show_alert=True)
            return

        await callback.answer()
        await _send_preview(callback.message, token, session, index, edit=True)

    @dp.callback_query(F.data.startswith("sd:"))
    async def result_details_callback(callback: CallbackQuery) -> None:
        locale = get_user_locale(callback.from_user.id)
        parts = (callback.data or "").split(":")
        if len(parts) != 3 or not parts[2].isdigit():
            await callback.answer(text("search", "invalid_result", locale=locale), show_alert=True)
            return

        _, token, index_text = parts
        session = SESSIONS.get(token)
        if session is None:
            await callback.answer(text("search", "expired", locale=locale), show_alert=True)
            return
        if session.owner_user_id != callback.from_user.id:
            await callback.answer(text("card", "not_owner", locale=locale), show_alert=True)
            return
        if callback.message is None:
            await callback.answer()
            return

        index = int(index_text)
        if index < 0 or index >= len(session.items):
            await callback.answer(text("search", "result_unavailable", locale=locale), show_alert=True)
            return

        candidate = session.items[index]
        await callback.answer()
        await aggregate_callback(callback.message, candidate, session.owner_user_id)
