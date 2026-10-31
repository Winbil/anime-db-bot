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
from core.runtime_metrics import RuntimeMetricsRegistry, RuntimeSourceDescriptor
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
from services.runtime.source_health import SourceHealthRegistry, SourceHealthSnapshot
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


def _source_health_line(snapshot: SourceHealthSnapshot, locale: str) -> str:
    state = _t(locale, f"source_health_state_{snapshot.state}")
    probe = _t(
        locale,
        "source_health_probe_yes"
        if snapshot.probe_in_flight
        else "source_health_probe_no",
    )
    return _t(
        locale,
        "source_health_line",
        source=snapshot.source,
        state=state,
        failures=snapshot.consecutive_failures,
        probe=probe,
    )


def _format_uptime(seconds: float) -> str:
    total = max(0, int(seconds))
    days, remainder = divmod(total, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, seconds = divmod(remainder, 60)
    parts: list[str] = []
    if days:
        parts.append(f"{days}d")
    if hours or days:
        parts.append(f"{hours}h")
    if minutes or hours or days:
        parts.append(f"{minutes}m")
    if not parts:
        parts.append(f"{seconds}s")
    return " ".join(parts)


def _format_latency(value: float | None) -> str:
    if value is None:
        return "—"
    if value < 10:
        return f"{value:.1f} ms"
    return f"{round(value):d} ms"


def _format_percent(value: float | None) -> str:
    return "—" if value is None else f"{value * 100:.1f}%"


def _runtime_source_state(
    descriptor: RuntimeSourceDescriptor,
    snapshot: SourceHealthSnapshot,
    *,
    calls_24h: int,
    errors_1h: int,
    limited_1h: int,
) -> str:
    if snapshot.circuit_open:
        return "OPEN"
    if snapshot.state == "half_open":
        return "RECOVERING"
    if descriptor.mode == "unavailable":
        return "UNAVAILABLE"
    if descriptor.mode == "local":
        return "LOCAL"
    if descriptor.mode == "limited":
        return "LIMITED"
    if limited_1h > 0:
        return "LIMITED"
    if calls_24h <= 0:
        return "IDLE"
    if errors_1h > 0:
        return "DEGRADED"
    return "OK"


def _status_source_line(
    descriptor: RuntimeSourceDescriptor,
    *,
    locale: str,
    health: SourceHealthRegistry,
    metrics: RuntimeMetricsRegistry,
) -> str:
    one_hour = metrics.source_window(descriptor.key, 3600)
    one_day = metrics.source_window(descriptor.key, 86400)
    snapshot = health.snapshot(descriptor.key)
    state = _runtime_source_state(
        descriptor,
        snapshot,
        calls_24h=one_day.calls,
        errors_1h=one_hour.errors,
        limited_1h=one_hour.limited,
    )
    latency = (
        one_hour.average_latency_ms
        if one_hour.average_latency_ms is not None
        else one_day.average_latency_ms
    )
    note = f" ({descriptor.note})" if descriptor.note else ""
    return _t(
        locale,
        "status_source_line",
        source=descriptor.display_name,
        state=state,
        note=note,
        latency=_format_latency(latency),
        calls=f"{one_hour.calls}/{one_day.calls}",
        errors=f"{one_hour.errors}/{one_day.errors}",
    )


def _status_lines(
    locale: str,
    *,
    source_health: SourceHealthRegistry,
    runtime_metrics: RuntimeMetricsRegistry,
    source_descriptors: tuple[RuntimeSourceDescriptor, ...],
) -> list[str]:
    windows = (
        ("1h", 3600),
        ("5h", 5 * 3600),
        ("10h", 10 * 3600),
        ("24h", 24 * 3600),
    )
    lines = [
        _t(locale, "status_title"),
        _t(
            locale,
            "status_uptime",
            value=_format_uptime(runtime_metrics.uptime_seconds),
        ),
        _t(locale, "status_process_note"),
        "",
        _t(locale, "status_sources"),
    ]
    if source_descriptors:
        lines.extend(
            _status_source_line(
                descriptor,
                locale=locale,
                health=source_health,
                metrics=runtime_metrics,
            )
            for descriptor in source_descriptors
        )
    else:
        lines.append(_t(locale, "status_no_sources"))

    day = runtime_metrics.window(86400)
    lines.extend(
        [
            "",
            _t(locale, "status_cache"),
            _t(
                locale,
                "status_cache_summary",
                rate=_format_percent(day.cache_hit_rate),
                hits=day.cache_hits,
                misses=day.cache_misses,
                expired=day.cache_expired,
            ),
        ]
    )
    for cache in runtime_metrics.cache_window(86400)[:5]:
        lines.append(
            _t(
                locale,
                "status_cache_line",
                cache=cache.name,
                rate=_format_percent(cache.hit_rate),
                accesses=cache.accesses,
            )
        )

    lines.extend(["", _t(locale, "status_load")])
    for label, seconds in windows:
        value = runtime_metrics.window(seconds)
        lines.append(
            _t(
                locale,
                "status_window_line",
                window=label,
                total=value.updates,
                updates=value.updates,
                sources=value.source_calls,
                errors=value.update_errors + value.source_errors,
            )
        )
    return lines


def register_admin_handlers(
    dp: Dispatcher,
    *,
    source_health: SourceHealthRegistry | None = None,
    runtime_metrics: RuntimeMetricsRegistry | None = None,
    source_descriptors: tuple[RuntimeSourceDescriptor, ...] = (),
) -> None:
    pending_mapping_mutations = ExpiringSessionStore[_PendingMappingMutation](
        max_entries=128,
        ttl_seconds=300,
        name="admin_mapping_mutation",
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

    @dp.message(Command("source_health"))
    async def source_health_handler(message: Message) -> None:
        admin_id, locale = await require_admin(message)
        if admin_id is None:
            return

        snapshots = source_health.snapshots() if source_health is not None else ()
        lines = [_source_health_line(snapshot, locale) for snapshot in snapshots]
        for chunk in _chunk_lines(
            _t(locale, "source_health_title", count=len(snapshots)),
            lines,
            empty_text=_t(locale, "source_health_empty"),
        ):
            await message.answer(chunk)

    @dp.message(Command("status"))
    async def status_handler(message: Message) -> None:
        admin_id, locale = await require_admin(message)
        if admin_id is None:
            return
        if source_health is None or runtime_metrics is None:
            await message.answer(_t(locale, "status_unavailable"))
            return

        lines = _status_lines(
            locale,
            source_health=source_health,
            runtime_metrics=runtime_metrics,
            source_descriptors=source_descriptors,
        )
        for chunk in _chunk_lines(
            lines[0],
            lines[1:],
            empty_text=_t(locale, "status_unavailable"),
        ):
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
