from __future__ import annotations

import logging
import re
import secrets
from collections.abc import Mapping
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
from bots.telegram.callbacks import (
    PagePickerCallback,
    TokenCallback,
    TokenIndexCallback,
    TokenValueCallback,
)
from bots.telegram.pagination import search_picker_callback, search_picker_keyboard
from bots.telegram.card.views.renderer import plain_text_to_rich_html
from core.contracts import AnimeSearchProvider
from core.models import SearchCandidate, SearchResultSet
from core.source_names import MAL_SOURCE_NAME
from localization import text
from search.registry import DEFAULT_SEARCH_PROVIDER_KEYS
from services.identity.direct_lookup import DirectIdLookupService
from services.search.service import SearchService
from services.search.expansion import expand_text_search
from services.users.settings import get_user_locale

MAX_SEARCH_SESSIONS = 200
MAX_SCOPE_SESSIONS = 200
MAX_PENDING_INPUTS = 500


ALL_PROVIDER_KEYS = tuple(str(key) for key in DEFAULT_SEARCH_PROVIDER_KEYS)

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


@dataclass(slots=True)
class SearchUiState:
    sessions: ExpiringSessionStore[SearchSession]
    scope_sessions: ExpiringSessionStore[ScopeSelectionSession]
    pending_inputs: ExpiringSessionStore[PendingAnimeInput]
    service_cache: dict[tuple[str, ...], SearchService] = field(default_factory=dict)

    @classmethod
    def create(cls, input_ttl_seconds: int) -> "SearchUiState":
        input_ttl = max(60, int(input_ttl_seconds))
        return cls(
            sessions=ExpiringSessionStore(
                max_entries=MAX_SEARCH_SESSIONS, name="search_results"
            ),
            scope_sessions=ExpiringSessionStore(
                max_entries=MAX_SCOPE_SESSIONS,
                ttl_seconds=input_ttl,
                name="search_scope",
            ),
            pending_inputs=ExpiringSessionStore(
                max_entries=MAX_PENDING_INPUTS,
                ttl_seconds=input_ttl,
                name="search_input",
            ),
        )


def _ui(locale: str, key: str, **kwargs: object) -> str:
    return text("search_ui", key, locale=locale, **kwargs)


def _normalize_provider_keys(keys: tuple[str, ...] | list[str]) -> tuple[str, ...]:
    requested = set(keys)
    return tuple(key for key in ALL_PROVIDER_KEYS if key in requested)


def _service_for(
    provider_keys: tuple[str, ...],
    default_service: SearchService,
    provider_map: Mapping[str, AnimeSearchProvider],
    service_cache: dict[tuple[str, ...], SearchService],
) -> SearchService:
    provider_keys = _normalize_provider_keys(provider_keys)
    if provider_keys == DEFAULT_SEARCH_PROVIDER_KEYS:
        return default_service

    service = service_cache.get(provider_keys)
    if service is None:
        if not provider_keys:
            raise ValueError("No search providers selected")
        service = SearchService(
            tuple(provider_map[key] for key in provider_keys),
            settings=default_service.settings,
        )
        service_cache[provider_keys] = service
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

    parts = [
        part.strip() for part in value.replace("+", ",").split(",") if part.strip()
    ]
    if not parts:
        return None

    keys: list[str] = []
    for part in parts:
        key = PROVIDER_ALIASES.get(part, part if part in ALL_PROVIDER_KEYS else None)
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
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(
                text=_ui(locale, "all"),
                callback_data=TokenValueCallback("sc", token, "all").encode(),
            )
        ]
    ]

    provider_buttons = [
        InlineKeyboardButton(
            text=_source_label(key),
            callback_data=TokenValueCallback("sc", token, key).encode(),
        )
        for key in ALL_PROVIDER_KEYS
    ]
    rows.extend(
        provider_buttons[index : index + 2]
        for index in range(0, len(provider_buttons), 2)
    )
    rows.append(
        [
            InlineKeyboardButton(
                text=_ui(locale, "cancel"),
                callback_data=TokenCallback("sx", token).encode(),
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _waiting_keyboard(token: str, locale: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=_ui(locale, "cancel"),
                    callback_data=TokenCallback("sx", token).encode(),
                )
            ]
        ]
    )


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
            InlineKeyboardButton(
                text="◀️",
                callback_data=TokenIndexCallback("sr", token, index - 1).encode(),
            )
        )

    suffix = "" if complete else "+"
    nav.append(
        InlineKeyboardButton(
            text=f"{index + 1}/{total}{suffix}",
            callback_data=(
                search_picker_callback(token, index, total) if total > 1 else "noop"
            ),
        )
    )
    if index + 1 < total:
        nav.append(
            InlineKeyboardButton(
                text="▶️",
                callback_data=TokenIndexCallback("sr", token, index + 1).encode(),
            )
        )

    return InlineKeyboardMarkup(
        inline_keyboard=[
            nav,
            [
                InlineKeyboardButton(
                    text=_ui(locale, "details"),
                    callback_data=TokenIndexCallback("sd", token, index).encode(),
                )
            ],
        ]
    )


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
            f"{_source_label(key)}: {candidate.external_ids[key]}" for key in ordered
        )
    else:
        lines.append(_ui(locale, "no_ids"))

    if session.errors:
        lines.extend(
            [
                "",
                _ui(locale, "unavailable", sources=", ".join(session.errors)),
            ]
        )
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
    state: SearchUiState,
    query: str,
    owner_user_id: int,
    result_set: SearchResultSet,
) -> str:
    token = secrets.token_urlsafe(6)
    state.sessions[token] = SearchSession(
        query=query,
        owner_user_id=int(owner_user_id),
        items=list(result_set.items),
        complete=result_set.complete,
        errors=dict(result_set.errors),
    )
    return token


def _remember_scope(state: SearchUiState, owner_user_id: int, chat_id: int) -> str:
    token = secrets.token_urlsafe(6)
    state.scope_sessions[token] = ScopeSelectionSession(
        owner_user_id=int(owner_user_id),
        chat_id=int(chat_id),
    )
    return token


def _pending_key(user_id: int) -> str:
    return str(int(user_id))


class PendingAnimeInputFilter(BaseFilter):
    """Match only the next text from the owner/chat of a live /anime flow."""

    def __init__(self, state: SearchUiState) -> None:
        self._state = state

    async def __call__(self, message: Message) -> bool:
        if (
            message.from_user is None
            or not message.text
            or message.text.startswith("/")
        ):
            return False
        pending = self._state.pending_inputs.get(_pending_key(message.from_user.id))
        return pending is not None and pending.chat_id == message.chat.id


def _clear_pending(state: SearchUiState, user_id: int) -> bool:
    key = _pending_key(user_id)
    if state.pending_inputs.get(key) is None:
        return False
    try:
        del state.pending_inputs[key]
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
    provider_map: Mapping[str, AnimeSearchProvider],
    state: SearchUiState,
) -> None:
    locale = get_user_locale(owner_user_id)
    parsed_direct = _parse_direct_query(query, direct_lookup.source_keys)

    try:
        if parsed_direct is not None:
            explicit_source, external_id = parsed_direct
            if explicit_source is not None:
                if (
                    direct_source_keys is not None
                    and explicit_source not in direct_source_keys
                ):
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
            service = _service_for(
                provider_keys, default_service, provider_map, state.service_cache
            )
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

    token = _remember_results(state, query, owner_user_id, result_set)
    await _send_preview(message, token, state.sessions[token], 0, edit=False)


def register_search_handlers(
    dp: Dispatcher,
    *,
    aggregate_callback: Callable[[Message, SearchCandidate, int], Awaitable[None]],
    default_service: SearchService,
    direct_lookup: DirectIdLookupService,
    provider_map: Mapping[str, AnimeSearchProvider],
    input_ttl_seconds: int,
) -> SearchUiState:
    """Register the single public anime-search command and its interactive flow."""
    provider_map = {str(key): provider for key, provider in provider_map.items()}
    state = SearchUiState.create(input_ttl_seconds)

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
                provider_map=provider_map,
                state=state,
            )
            return

        token = _remember_scope(state, user_id, message.chat.id)
        await message.answer(
            _ui(locale, "choose_source"),
            reply_markup=_scope_keyboard(token, locale),
        )

    @dp.message(Command("cancel"))
    async def cancel_search_handler(message: Message) -> None:
        user_id = message.from_user.id if message.from_user else 0
        locale = get_user_locale(user_id)
        if _clear_pending(state, user_id):
            await message.answer(_ui(locale, "cancelled"))
        else:
            await message.answer(_ui(locale, "nothing_pending"))

    @dp.callback_query(F.data.startswith("sc:"))
    async def scope_callback(callback: CallbackQuery) -> None:
        locale = get_user_locale(callback.from_user.id)
        data = TokenValueCallback.parse(callback.data, prefix="sc")
        if data is None:
            await callback.answer(
                text("search", "invalid_provider", locale=locale), show_alert=True
            )
            return

        token = data.token
        selected = data.value
        scope_session = state.scope_sessions.get(token)
        if scope_session is None:
            await callback.answer(_ui(locale, "expired"), show_alert=True)
            return
        if scope_session.owner_user_id != callback.from_user.id:
            await callback.answer(
                text("card", "not_owner", locale=locale), show_alert=True
            )
            return
        if callback.message is None:
            await callback.answer()
            return

        if selected == "all":
            provider_keys = ALL_PROVIDER_KEYS
            direct_source_keys = None
            scope_label = _ui(locale, "all")
        elif selected in provider_map:
            provider_keys = (selected,)
            direct_source_keys = (selected,)
            scope_label = _source_label(selected)
        else:
            await callback.answer(
                text("search", "invalid_provider", locale=locale), show_alert=True
            )
            return

        state.pending_inputs[_pending_key(callback.from_user.id)] = PendingAnimeInput(
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
        data = TokenCallback.parse(callback.data, prefix="sx")
        if data is None:
            await callback.answer()
            return
        token = data.token
        scope_session = state.scope_sessions.get(token)
        if (
            scope_session is not None
            and scope_session.owner_user_id != callback.from_user.id
        ):
            await callback.answer(
                text("card", "not_owner", locale=locale), show_alert=True
            )
            return

        _clear_pending(state, callback.from_user.id)
        try:
            del state.scope_sessions[token]
        except KeyError:
            pass
        await callback.answer()
        if callback.message is not None:
            await callback.message.edit_text(
                _ui(locale, "cancelled"), reply_markup=None
            )

    @dp.message(PendingAnimeInputFilter(state))
    async def pending_anime_input_handler(message: Message) -> None:
        user_id = message.from_user.id if message.from_user else 0
        pending = state.pending_inputs.get(_pending_key(user_id))
        if pending is None or pending.chat_id != message.chat.id:
            return

        _clear_pending(state, user_id)
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
            provider_map=provider_map,
            state=state,
        )

    @dp.callback_query(F.data.startswith("sp:"))
    async def search_page_picker_callback_handler(callback: CallbackQuery) -> None:
        locale = get_user_locale(callback.from_user.id)
        data = PagePickerCallback.parse(callback.data, prefix="sp")
        if data is None:
            await callback.answer(
                text("search", "invalid_page", locale=locale), show_alert=True
            )
            return
        session = state.sessions.get(data.token)
        if session is None:
            await callback.answer(
                text("search", "expired", locale=locale), show_alert=True
            )
            return
        if session.owner_user_id != callback.from_user.id:
            await callback.answer(
                text("card", "not_owner", locale=locale), show_alert=True
            )
            return
        if callback.message is None:
            await callback.answer()
            return
        if not session.items:
            await callback.answer(
                text("search", "result_unavailable", locale=locale), show_alert=True
            )
            return
        current = max(0, min(data.current, len(session.items) - 1))
        total = len(session.items)
        picker = PagePickerCallback(
            "sp",
            data.token,
            "sr",
            current,
            total,
            data.window,
        )
        await callback.answer()
        await callback.message.edit_reply_markup(
            reply_markup=search_picker_keyboard(picker, locale=locale)
        )

    @dp.callback_query(F.data.startswith("sr:"))
    async def result_page_callback(callback: CallbackQuery) -> None:
        locale = get_user_locale(callback.from_user.id)
        data = TokenIndexCallback.parse(callback.data, prefix="sr")
        if data is None:
            await callback.answer(
                text("search", "invalid_page", locale=locale), show_alert=True
            )
            return

        token = data.token
        session = state.sessions.get(token)
        if session is None:
            await callback.answer(
                text("search", "expired", locale=locale), show_alert=True
            )
            return
        if session.owner_user_id != callback.from_user.id:
            await callback.answer(
                text("card", "not_owner", locale=locale), show_alert=True
            )
            return
        if callback.message is None:
            await callback.answer()
            return

        index = data.index
        if index < 0 or index >= len(session.items):
            await callback.answer(
                text("search", "result_unavailable", locale=locale), show_alert=True
            )
            return

        await callback.answer()
        await _send_preview(callback.message, token, session, index, edit=True)

    @dp.callback_query(F.data.startswith("sd:"))
    async def result_details_callback(callback: CallbackQuery) -> None:
        locale = get_user_locale(callback.from_user.id)
        data = TokenIndexCallback.parse(callback.data, prefix="sd")
        if data is None:
            await callback.answer(
                text("search", "invalid_result", locale=locale), show_alert=True
            )
            return

        token = data.token
        session = state.sessions.get(token)
        if session is None:
            await callback.answer(
                text("search", "expired", locale=locale), show_alert=True
            )
            return
        if session.owner_user_id != callback.from_user.id:
            await callback.answer(
                text("card", "not_owner", locale=locale), show_alert=True
            )
            return
        if callback.message is None:
            await callback.answer()
            return

        index = data.index
        if index < 0 or index >= len(session.items):
            await callback.answer(
                text("search", "result_unavailable", locale=locale), show_alert=True
            )
            return

        candidate = session.items[index]
        await callback.answer()
        await aggregate_callback(callback.message, candidate, session.owner_user_id)

    return state
