from __future__ import annotations

import secrets
import sqlite3
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from aiogram import BaseMiddleware, Dispatcher
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message, TelegramObject

from bots.session_store import ExpiringSessionStore
from localization import text
from mappings.resolver import (
    MappingOverride,
    MappingOverrideHistory,
    delete_mapping_override,
    list_mapping_override_history,
    list_mapping_overrides,
    set_mapping_override,
)
from services.users.access_control import is_telegram_admin
from services.users.bans import BanRecord, ban_user, get_active_ban, unban_user
from services.users.settings import (
    get_user_locale,
    list_platform_user_ids,
    touch_platform_user,
)


@dataclass(frozen=True, slots=True)
class _PendingMappingMutation:
    admin_id: int
    operation: str
    source_provider: str
    source_id: str
    target_provider: str
    target_id: str
    reason: str
    action: str | None = None


def _t(locale: str, key: str, **params: object) -> str:
    return text("admin", key, locale=locale, **params)


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


def _looks_like_integer(raw: str) -> bool:
    value = raw.strip()
    return bool(value) and value.lstrip("+-").isdecimal()


def _parse_ban_arguments(
    text_value: str | None,
) -> tuple[int, int | None, str | None] | None:
    parts = (text_value or "").split()
    if len(parts) < 2:
        return None

    user_id = _parse_positive_int(parts[1])
    if user_id is None:
        return None

    remaining = parts[2:]
    duration: int | None = None
    if remaining and _looks_like_integer(remaining[0]):
        duration = _parse_positive_int(remaining[0])
        if duration is None:
            return None
        remaining = remaining[1:]
    elif len(remaining) > 1 and _looks_like_integer(remaining[-1]):
        duration = _parse_positive_int(remaining[-1])
        if duration is None:
            return None
        remaining = remaining[:-1]

    reason = " ".join(remaining).strip() or None
    return user_id, duration, reason


def _clean_admin_field(value: object) -> str:
    return " ".join(str(value or "").split()).strip()


def _clip_admin_field(value: object, limit: int = 900) -> str:
    cleaned = _clean_admin_field(value)
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: max(1, limit - 1)] + "…"


def _clean_mapping_route_part(value: object) -> str:
    return _clean_admin_field(value).casefold()


def _parse_mapping_set(
    text_value: str | None,
) -> tuple[str, str, str, str, str, str] | None:
    parts = (text_value or "").split(maxsplit=6)
    if len(parts) != 7:
        return None
    _, action, source_provider, source_id, target_provider, target_id, reason = parts
    action = action.strip().casefold()
    source_provider = _clean_mapping_route_part(source_provider)
    source_id = _clean_admin_field(source_id)
    target_provider = _clean_mapping_route_part(target_provider)
    target_id = _clean_admin_field(target_id)
    reason = _clean_admin_field(reason)
    if (
        action not in {"accept", "reject"}
        or not source_provider
        or not source_id
        or not target_provider
        or not target_id
        or source_provider == target_provider
        or not reason
    ):
        return None
    return action, source_provider, source_id, target_provider, target_id, reason


def _parse_mapping_delete(
    text_value: str | None,
) -> tuple[str, str, str, str, str] | None:
    parts = (text_value or "").split(maxsplit=5)
    if len(parts) != 6:
        return None
    _, source_provider, source_id, target_provider, target_id, reason = parts
    source_provider = _clean_mapping_route_part(source_provider)
    source_id = _clean_admin_field(source_id)
    target_provider = _clean_mapping_route_part(target_provider)
    target_id = _clean_admin_field(target_id)
    reason = _clean_admin_field(reason)
    if (
        not source_provider
        or not source_id
        or not target_provider
        or not target_id
        or source_provider == target_provider
        or not reason
    ):
        return None
    return source_provider, source_id, target_provider, target_id, reason


def _mapping_mutation_preview(item: _PendingMappingMutation) -> str:
    route = (
        f"{item.source_provider}:{item.source_id} → "
        f"{item.target_provider}:{item.target_id}"
    )
    if item.operation == "set":
        return f"SET {item.action} {route} | reason={_clip_admin_field(item.reason)}"
    return f"DELETE {route} | reason={_clip_admin_field(item.reason)}"


def _chunk_lines(
    title: str,
    lines: list[str],
    *,
    empty_text: str,
    limit: int = 3500,
) -> list[str]:
    if not lines:
        return [empty_text]

    chunks: list[str] = []
    current = title
    for raw_line in lines:
        line = _clip_admin_field(raw_line, max(1, limit - 32))
        addition = f"\n{line}"
        if len(current) + len(addition) > limit:
            chunks.append(current)
            current = line
        else:
            current += addition
    chunks.append(current)
    return chunks


def _mapping_override_line(item: MappingOverride) -> str:
    route = (
        f"{item.source_provider}:{item.source_id} → "
        f"{item.target_provider}:{item.target_id}"
    )
    parts = [f"[{item.action}] {route}", f"reason={_clip_admin_field(item.reason)}"]
    if item.author:
        parts.append(f"author={_clip_admin_field(item.author, 200)}")
    if item.updated_at:
        parts.append(f"updated={_clip_admin_field(item.updated_at, 100)}")
    return " | ".join(parts)


def _mapping_history_line(item: MappingOverrideHistory) -> str:
    route = (
        f"{item.source_provider}:{item.source_id} → "
        f"{item.target_provider}:{item.target_id}"
    )
    parts = [
        _clip_admin_field(item.changed_at, 100),
        f"{item.event} {item.override_action}",
        route,
        f"reason={_clip_admin_field(item.reason)}",
    ]
    if item.author:
        parts.append(f"author={_clip_admin_field(item.author, 200)}")
    return " | ".join(part for part in parts if part)


def _parse_mapping_history_limit(text_value: str | None) -> int | None:
    parts = (text_value or "").split()
    if len(parts) == 1:
        return 20
    if len(parts) != 2:
        return None
    value = _parse_positive_int(parts[1])
    if value is None or value > 100:
        return None
    return value


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
    pending_mapping_mutations = ExpiringSessionStore[_PendingMappingMutation](
        max_entries=128,
        ttl_seconds=300,
    )

    def new_mapping_token() -> str:
        while True:
            token = secrets.token_hex(4)
            if token not in pending_mapping_mutations:
                return token

    async def require_admin(message: Message) -> tuple[int | None, str]:
        admin_id = int(message.from_user.id) if message.from_user else None
        locale = get_user_locale(admin_id)
        if admin_id is None or not is_telegram_admin(admin_id):
            await message.answer(_t(locale, "forbidden"))
            return None, locale
        return admin_id, locale

    @dp.message(Command("users"))
    async def users_handler(message: Message) -> None:
        admin_id, locale = await require_admin(message)
        if admin_id is None:
            return

        for chunk in _chunk_user_ids(list_platform_user_ids("telegram"), locale):
            await message.answer(chunk)

    @dp.message(Command("mapping_overrides"))
    async def mapping_overrides_handler(message: Message) -> None:
        admin_id, locale = await require_admin(message)
        if admin_id is None:
            return

        overrides = list_mapping_overrides()
        lines = [_mapping_override_line(item) for item in overrides]
        for chunk in _chunk_lines(
            _t(locale, "mapping_overrides_title", count=len(overrides)),
            lines,
            empty_text=_t(locale, "mapping_overrides_empty"),
        ):
            await message.answer(chunk)

    @dp.message(Command("mapping_history"))
    async def mapping_history_handler(message: Message) -> None:
        admin_id, locale = await require_admin(message)
        if admin_id is None:
            return

        limit = _parse_mapping_history_limit(message.text)
        if limit is None:
            await message.answer(_t(locale, "mapping_history_usage"))
            return

        history = list_mapping_override_history(limit=limit, newest_first=True)
        lines = [_mapping_history_line(item) for item in history]
        for chunk in _chunk_lines(
            _t(locale, "mapping_history_title", shown=len(history)),
            lines,
            empty_text=_t(locale, "mapping_history_empty"),
        ):
            await message.answer(chunk)

    @dp.message(Command("mapping_set"))
    async def mapping_set_handler(message: Message) -> None:
        admin_id, locale = await require_admin(message)
        if admin_id is None:
            return

        parsed = _parse_mapping_set(message.text)
        if parsed is None:
            await message.answer(_t(locale, "mapping_set_usage"))
            return
        action, source_provider, source_id, target_provider, target_id, reason = parsed
        pending = _PendingMappingMutation(
            admin_id=admin_id,
            operation="set",
            source_provider=source_provider,
            source_id=source_id,
            target_provider=target_provider,
            target_id=target_id,
            reason=reason,
            action=action,
        )
        token = new_mapping_token()
        pending_mapping_mutations[token] = pending
        await message.answer(
            _t(
                locale,
                "mapping_pending",
                preview=_mapping_mutation_preview(pending),
                token=token,
            )
        )

    @dp.message(Command("mapping_delete"))
    async def mapping_delete_handler(message: Message) -> None:
        admin_id, locale = await require_admin(message)
        if admin_id is None:
            return

        parsed = _parse_mapping_delete(message.text)
        if parsed is None:
            await message.answer(_t(locale, "mapping_delete_usage"))
            return
        source_provider, source_id, target_provider, target_id, reason = parsed
        pending = _PendingMappingMutation(
            admin_id=admin_id,
            operation="delete",
            source_provider=source_provider,
            source_id=source_id,
            target_provider=target_provider,
            target_id=target_id,
            reason=reason,
        )
        token = new_mapping_token()
        pending_mapping_mutations[token] = pending
        await message.answer(
            _t(
                locale,
                "mapping_pending",
                preview=_mapping_mutation_preview(pending),
                token=token,
            )
        )

    @dp.message(Command("mapping_confirm"))
    async def mapping_confirm_handler(message: Message) -> None:
        admin_id, locale = await require_admin(message)
        if admin_id is None:
            return

        parts = (message.text or "").split()
        if len(parts) != 2:
            await message.answer(_t(locale, "mapping_confirm_usage"))
            return
        token = parts[1].strip().casefold()
        pending = pending_mapping_mutations.get(token)
        if pending is None:
            await message.answer(_t(locale, "mapping_confirm_missing"))
            return
        if pending.admin_id != admin_id:
            await message.answer(_t(locale, "mapping_confirm_owner"))
            return

        preview = _mapping_mutation_preview(pending)
        author = f"telegram:{admin_id}"
        try:
            if pending.operation == "set":
                set_mapping_override(
                    pending.source_provider,
                    pending.source_id,
                    pending.target_provider,
                    pending.target_id,
                    action=pending.action or "",
                    reason=pending.reason,
                    author=author,
                )
                response_key = "mapping_confirmed_set"
            else:
                deleted = delete_mapping_override(
                    pending.source_provider,
                    pending.source_id,
                    pending.target_provider,
                    pending.target_id,
                    reason=pending.reason,
                    author=author,
                )
                if not deleted:
                    del pending_mapping_mutations[token]
                    await message.answer(_t(locale, "mapping_delete_missing"))
                    return
                response_key = "mapping_confirmed_delete"
        except (FileNotFoundError, OSError, ValueError, sqlite3.Error) as exc:
            await message.answer(
                _t(
                    locale,
                    "mapping_mutation_failed",
                    error=_clip_admin_field(exc, 500),
                )
            )
            return

        del pending_mapping_mutations[token]
        await message.answer(_t(locale, response_key, preview=preview))

    @dp.message(Command("mapping_cancel"))
    async def mapping_cancel_handler(message: Message) -> None:
        admin_id, locale = await require_admin(message)
        if admin_id is None:
            return

        parts = (message.text or "").split()
        if len(parts) != 2:
            await message.answer(_t(locale, "mapping_cancel_usage"))
            return
        token = parts[1].strip().casefold()
        pending = pending_mapping_mutations.get(token)
        if pending is None:
            await message.answer(_t(locale, "mapping_confirm_missing"))
            return
        if pending.admin_id != admin_id:
            await message.answer(_t(locale, "mapping_confirm_owner"))
            return
        del pending_mapping_mutations[token]
        await message.answer(_t(locale, "mapping_cancelled"))

    @dp.message(Command("ban"))
    async def ban_handler(message: Message) -> None:
        admin_id, locale = await require_admin(message)
        if admin_id is None:
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
            banned_by=admin_id,
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
        admin_id, locale = await require_admin(message)
        if admin_id is None:
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
