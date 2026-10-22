from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware, Dispatcher
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message, TelegramObject

from services.access_control import is_telegram_admin
from services.bans import BanRecord, ban_user, get_active_ban, unban_user
from services.user_settings import (
    get_user_locale,
    list_platform_user_ids,
    touch_platform_user,
)


_ADMIN_TEXT = {
    "ru": {
        "forbidden": "Недостаточно прав.",
        "users_title": "Сохранённые Telegram ID: {count}",
        "users_empty": "Сохранённых Telegram ID пока нет.",
        "ban_usage": (
            "Использование: /ban <user_id> [seconds] [reason]\n"
            "Без seconds бан постоянный. Также поддерживается: /ban <user_id> <reason> <seconds>."
        ),
        "invalid_id": "user_id должен быть положительным числом.",
        "invalid_duration": "Время бана должно быть положительным числом секунд.",
        "admin_target": "Администратора нельзя заблокировать.",
        "ban_permanent": "Пользователь {user_id} заблокирован навсегда.{reason}",
        "ban_temporary": "Пользователь {user_id} заблокирован на {seconds} сек.{reason}",
        "unban_usage": "Использование: /unban <user_id>",
        "unbanned": "Блокировка пользователя {user_id} снята.",
        "not_banned": "Пользователь {user_id} не был заблокирован.",
        "banned_permanent": "Доступ к боту заблокирован навсегда.{reason}",
        "banned_temporary": "Доступ к боту заблокирован ещё на {seconds} сек.{reason}",
        "reason": "\nПричина: {reason}",
    },
    "en": {
        "forbidden": "Insufficient permissions.",
        "users_title": "Saved Telegram IDs: {count}",
        "users_empty": "No Telegram IDs have been saved yet.",
        "ban_usage": (
            "Usage: /ban <user_id> [seconds] [reason]\n"
            "Without seconds the ban is permanent. Also supported: /ban <user_id> <reason> <seconds>."
        ),
        "invalid_id": "user_id must be a positive number.",
        "invalid_duration": "Ban duration must be a positive number of seconds.",
        "admin_target": "An administrator cannot be banned.",
        "ban_permanent": "User {user_id} was banned permanently.{reason}",
        "ban_temporary": "User {user_id} was banned for {seconds} seconds.{reason}",
        "unban_usage": "Usage: /unban <user_id>",
        "unbanned": "User {user_id} was unbanned.",
        "not_banned": "User {user_id} was not banned.",
        "banned_permanent": "Access to the bot is permanently blocked.{reason}",
        "banned_temporary": "Access to the bot is blocked for another {seconds} seconds.{reason}",
        "reason": "\nReason: {reason}",
    },
}


def _t(locale: str, key: str, **params: object) -> str:
    language = "en" if locale == "en" else "ru"
    value = _ADMIN_TEXT[language][key]
    try:
        return value.format(**params)
    except (KeyError, ValueError):
        return value


def _reason_suffix(locale: str, reason: str | None) -> str:
    if not reason:
        return ""
    return _t(locale, "reason", reason=reason)


def _ban_notice(locale: str, ban: BanRecord) -> str:
    reason = _reason_suffix(locale, ban.reason)
    if ban.expires_at is None:
        return _t(locale, "banned_permanent", reason=reason)
    remaining = max(1, ban.expires_at - int(time.time()))
    return _t(locale, "banned_temporary", seconds=remaining, reason=reason)


def _parse_positive_int(raw: str) -> int | None:
    if not raw.isdecimal():
        return None
    value = int(raw)
    return value if value > 0 else None


def _parse_ban_arguments(text_value: str | None) -> tuple[int, int | None, str | None] | None:
    parts = (text_value or "").split()
    if len(parts) < 2:
        return None

    user_id = _parse_positive_int(parts[1])
    if user_id is None:
        return None

    remaining = parts[2:]
    duration: int | None = None
    if remaining:
        candidate = _parse_positive_int(remaining[0])
        if candidate is not None:
            duration = candidate
            remaining = remaining[1:]
        elif len(remaining) > 1:
            candidate = _parse_positive_int(remaining[-1])
            if candidate is not None:
                duration = candidate
                remaining = remaining[:-1]

    reason = " ".join(remaining).strip() or None
    return user_id, duration, reason


def _chunk_user_ids(user_ids: list[int], locale: str) -> list[str]:
    if not user_ids:
        return [_t(locale, "users_empty")]

    title = _t(locale, "users_title", count=len(user_ids))
    chunks: list[str] = []
    current = title
    for user_id in user_ids:
        line = f"\n{user_id}"
        if len(current) + len(line) > 3500:
            chunks.append(current)
            current = line.lstrip()
        else:
            current += line
    chunks.append(current)
    return chunks


class TelegramModerationMiddleware(BaseMiddleware):
    """Register seen users and stop banned accounts before application handlers."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = getattr(event, "from_user", None)
        if user is None:
            return await handler(event, data)

        user_id = int(user.id)
        touch_platform_user("telegram", user_id)

        if is_telegram_admin(user_id):
            return await handler(event, data)

        ban = get_active_ban("telegram", user_id)
        if ban is None:
            return await handler(event, data)

        locale = get_user_locale(user_id)
        notice = _ban_notice(locale, ban)
        if isinstance(event, CallbackQuery):
            await event.answer(notice, show_alert=True)
        elif isinstance(event, Message):
            await event.answer(notice)
        return None


def register_admin_handlers(dp: Dispatcher) -> None:
    @dp.message(Command("users"))
    async def users_handler(message: Message) -> None:
        user_id = message.from_user.id if message.from_user else None
        locale = get_user_locale(user_id)
        if not is_telegram_admin(user_id):
            await message.answer(_t(locale, "forbidden"))
            return

        for chunk in _chunk_user_ids(list_platform_user_ids("telegram"), locale):
            await message.answer(chunk)

    @dp.message(Command("ban"))
    async def ban_handler(message: Message) -> None:
        admin_id = message.from_user.id if message.from_user else None
        locale = get_user_locale(admin_id)
        if not is_telegram_admin(admin_id):
            await message.answer(_t(locale, "forbidden"))
            return

        parsed = _parse_ban_arguments(message.text)
        if parsed is None:
            await message.answer(_t(locale, "ban_usage"))
            return

        target_id, duration, reason = parsed
        if is_telegram_admin(target_id):
            await message.answer(_t(locale, "admin_target"))
            return

        ban_user(
            "telegram",
            target_id,
            banned_by=int(admin_id),
            duration_seconds=duration,
            reason=reason,
        )
        reason_suffix = _reason_suffix(locale, reason)
        if duration is None:
            await message.answer(
                _t(locale, "ban_permanent", user_id=target_id, reason=reason_suffix)
            )
        else:
            await message.answer(
                _t(
                    locale,
                    "ban_temporary",
                    user_id=target_id,
                    seconds=duration,
                    reason=reason_suffix,
                )
            )

    @dp.message(Command("unban"))
    async def unban_handler(message: Message) -> None:
        admin_id = message.from_user.id if message.from_user else None
        locale = get_user_locale(admin_id)
        if not is_telegram_admin(admin_id):
            await message.answer(_t(locale, "forbidden"))
            return

        parts = (message.text or "").split()
        if len(parts) != 2:
            await message.answer(_t(locale, "unban_usage"))
            return
        target_id = _parse_positive_int(parts[1])
        if target_id is None:
            await message.answer(_t(locale, "invalid_id"))
            return

        if unban_user("telegram", target_id):
            await message.answer(_t(locale, "unbanned", user_id=target_id))
        else:
            await message.answer(_t(locale, "not_banned", user_id=target_id))
