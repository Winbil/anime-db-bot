from __future__ import annotations

from aiogram import Dispatcher, F
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, Message

from bots.telegram.card.constants import SECTION_LABELS, SOURCE_SELECTABLE_SECTIONS
from bots.telegram.card.characters import edit_characters_view
from bots.telegram.card.episodes import edit_episode_detail, edit_episodes_view
from bots.telegram.card.trailers import edit_trailers_view
from bots.telegram.card.renderer import (
    edit_anime_view,
    edit_description_view,
    edit_source_section_view,
)
from bots.telegram.card.selectors import description_sources, source_section_sources
from bots.telegram.card.service import SEARCH_SERVICE, SOURCES
from bots.telegram.card.state import ANIME_SESSIONS, AnimeCardSession
from bots.telegram.settings import register_settings_handlers
from localization import text
from services.user_settings import get_user_locale


def _session_for_callback(callback: CallbackQuery, token: str) -> AnimeCardSession | None:
    session = ANIME_SESSIONS.get(token)
    if session is None or session.owner_user_id != callback.from_user.id:
        return None
    return session


def build_dispatcher(mode_name: str) -> Dispatcher:
    """Build the core Telegram dispatcher without search-provider-specific handlers."""
    dp = Dispatcher()
    register_settings_handlers(dp)

    @dp.message(CommandStart())
    async def start_handler(message: Message) -> None:
        user_id = message.from_user.id if message.from_user else None
        locale = get_user_locale(user_id)
        source_names = ", ".join(source.name for source in SOURCES) or text(
            "start", "no_sources", locale=locale
        )
        lines = [
            text("start", "greeting", locale=locale),
            "",
            text("start", "telegram_mode", locale=locale, mode=mode_name),
            text(
                "start",
                "default_search",
                locale=locale,
                providers=SEARCH_SERVICE.provider_name,
            ),
            text("start", "data_sources", locale=locale, sources=source_names),
            "",
            text("start", "merge_note", locale=locale),
            "",
            text("start", "commands", locale=locale),
            text("start", "anime", locale=locale),
            text("start", "settings", locale=locale),
            text("start", "ping", locale=locale),
        ]
        await message.answer("\n".join(lines))

    @dp.message(Command("ping"))
    async def ping_handler(message: Message) -> None:
        await message.answer("pong")

    @dp.callback_query(F.data == "noop")
    async def noop_callback(callback: CallbackQuery) -> None:
        await callback.answer()

    @dp.callback_query(F.data.startswith("ad:"))
    async def description_source_callback_handler(callback: CallbackQuery) -> None:
        locale = get_user_locale(callback.from_user.id)
        data = (callback.data or "").split(":")
        if len(data) != 4 or not data[2].isdigit() or not data[3].isdigit():
            await callback.answer(
                text("card", "invalid_description", locale=locale), show_alert=True
            )
            return

        _, token, source_index_text, page_text = data
        raw_session = ANIME_SESSIONS.get(token)
        if raw_session is None:
            await callback.answer(text("card", "expired", locale=locale), show_alert=True)
            return
        if raw_session.owner_user_id != callback.from_user.id:
            await callback.answer(text("card", "not_owner", locale=locale), show_alert=True)
            return
        anime = raw_session.anime
        if callback.message is None:
            await callback.answer()
            return

        source_index = int(source_index_text)
        if source_index >= len(description_sources(anime)):
            await callback.answer(
                text("card", "description_source_unavailable", locale=locale),
                show_alert=True,
            )
            return

        await callback.answer()
        await edit_description_view(
            callback.message,
            token,
            anime,
            source_index=source_index,
            page=int(page_text),
            locale=locale,
        )

    @dp.callback_query(F.data.startswith("as:"))
    async def source_section_callback_handler(callback: CallbackQuery) -> None:
        locale = get_user_locale(callback.from_user.id)
        data = (callback.data or "").split(":")
        if (
            len(data) != 5
            or data[2] not in SOURCE_SELECTABLE_SECTIONS
            or not data[3].isdigit()
            or not data[4].isdigit()
        ):
            await callback.answer(
                text("card", "invalid_source", locale=locale), show_alert=True
            )
            return

        _, token, section, source_index_text, page_text = data
        raw_session = ANIME_SESSIONS.get(token)
        if raw_session is None:
            await callback.answer(text("card", "expired", locale=locale), show_alert=True)
            return
        if raw_session.owner_user_id != callback.from_user.id:
            await callback.answer(text("card", "not_owner", locale=locale), show_alert=True)
            return
        anime = raw_session.anime
        if callback.message is None:
            await callback.answer()
            return

        sources = source_section_sources(anime, section)
        source_index = int(source_index_text)
        if source_index >= len(sources):
            await callback.answer(
                text("card", "source_unavailable", locale=locale), show_alert=True
            )
            return

        await callback.answer()
        await edit_source_section_view(
            callback.message,
            token,
            anime,
            section,
            source_index,
            int(page_text),
            locale=locale,
        )

    @dp.callback_query(F.data.startswith("ae:"))
    async def episode_detail_callback_handler(callback: CallbackQuery) -> None:
        locale = get_user_locale(callback.from_user.id)
        data = (callback.data or "").split(":")
        if len(data) != 4 or not data[2].isdigit() or not data[3].isdigit():
            await callback.answer(
                text("card", "invalid_command", locale=locale), show_alert=True
            )
            return

        _, token, episode_text, return_page_text = data
        session = _session_for_callback(callback, token)
        if session is None:
            raw_session = ANIME_SESSIONS.get(token)
            key = "not_owner" if raw_session is not None else "expired"
            await callback.answer(text("card", key, locale=locale), show_alert=True)
            return
        if callback.message is None:
            await callback.answer()
            return

        await callback.answer()
        await edit_episode_detail(
            callback.message,
            token,
            session,
            episode_number=int(episode_text),
            return_page=int(return_page_text),
            locale=locale,
        )

    @dp.callback_query(F.data.startswith("ac:"))
    async def character_source_callback_handler(callback: CallbackQuery) -> None:
        locale = get_user_locale(callback.from_user.id)
        data = (callback.data or "").split(":")
        if len(data) != 4 or not data[2].isdigit() or not data[3].isdigit():
            await callback.answer(text("card", "invalid_source", locale=locale), show_alert=True)
            return

        _, token, source_index_text, page_text = data
        session = _session_for_callback(callback, token)
        if session is None:
            raw_session = ANIME_SESSIONS.get(token)
            key = "not_owner" if raw_session is not None else "expired"
            await callback.answer(text("card", key, locale=locale), show_alert=True)
            return
        if callback.message is None:
            await callback.answer()
            return

        await callback.answer()
        try:
            await edit_characters_view(
                callback.message,
                token,
                session,
                source_index=int(source_index_text),
                page=int(page_text),
                locale=locale,
            )
        except ValueError:
            await edit_characters_view(
                callback.message,
                token,
                session,
                source_index=None,
                page=0,
                locale=locale,
            )

    @dp.callback_query(F.data.startswith("at:"))
    async def trailer_source_callback_handler(callback: CallbackQuery) -> None:
        locale = get_user_locale(callback.from_user.id)
        data = (callback.data or "").split(":")
        if len(data) != 4 or not data[2].isdigit() or not data[3].isdigit():
            await callback.answer(
                text("card", "invalid_source", locale=locale), show_alert=True
            )
            return

        _, token, source_index_text, page_text = data
        session = _session_for_callback(callback, token)
        if session is None:
            raw_session = ANIME_SESSIONS.get(token)
            key = "not_owner" if raw_session is not None else "expired"
            await callback.answer(text("card", key, locale=locale), show_alert=True)
            return
        if callback.message is None:
            await callback.answer()
            return

        await callback.answer()
        try:
            await edit_trailers_view(
                callback.message,
                token,
                session,
                source_index=int(source_index_text),
                page=int(page_text),
                locale=locale,
            )
        except ValueError:
            await edit_trailers_view(
                callback.message,
                token,
                session,
                source_index=None,
                page=0,
                locale=locale,
            )

    @dp.callback_query(F.data.startswith("av:"))
    async def anime_view_callback_handler(callback: CallbackQuery) -> None:
        locale = get_user_locale(callback.from_user.id)
        data = (callback.data or "").split(":")
        if len(data) != 4 or not data[3].isdigit():
            await callback.answer(
                text("card", "invalid_command", locale=locale), show_alert=True
            )
            return

        _, token, section, page_text = data
        raw_session = ANIME_SESSIONS.get(token)
        if raw_session is None:
            await callback.answer(text("card", "expired", locale=locale), show_alert=True)
            return
        if raw_session.owner_user_id != callback.from_user.id:
            await callback.answer(text("card", "not_owner", locale=locale), show_alert=True)
            return
        anime = raw_session.anime
        if section not in SECTION_LABELS:
            await callback.answer(
                text("card", "invalid_section", locale=locale), show_alert=True
            )
            return
        if callback.message is None:
            await callback.answer()
            return

        await callback.answer()
        if section == "episodes":
            await edit_episodes_view(
                callback.message,
                token,
                raw_session,
                view_page=int(page_text),
                locale=locale,
            )
            return
        if section == "characters":
            await edit_characters_view(
                callback.message,
                token,
                raw_session,
                source_index=None,
                page=int(page_text),
                locale=locale,
            )
            return
        if section == "trailers":
            await edit_trailers_view(
                callback.message,
                token,
                raw_session,
                source_index=None,
                page=0,
                locale=locale,
            )
            return

        await edit_anime_view(
            callback.message,
            token,
            anime,
            section=section,
            page=int(page_text),
            locale=locale,
        )

    return dp
