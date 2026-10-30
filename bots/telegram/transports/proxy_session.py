from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncGenerator
from typing import Any, TypeVar, cast

from aiogram import Bot
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.session.base import BaseSession
from aiogram.client.telegram import PRODUCTION, TelegramAPIServer
from aiogram.exceptions import TelegramNetworkError, TelegramServerError
from aiogram.methods import TelegramMethod

from core.proxy_config import ProxyEntry

TelegramType = TypeVar("TelegramType")


class ProxyPoolAiohttpSession(BaseSession):
    """Aiogram session with round-robin proxy selection and network failover."""

    def __init__(
        self,
        proxies: tuple[ProxyEntry, ...],
        *,
        api: TelegramAPIServer = PRODUCTION,
        timeout: float = 60.0,
    ) -> None:
        if not proxies:
            raise ValueError("ProxyPoolAiohttpSession requires at least one proxy")
        super().__init__(api=api, timeout=timeout)
        self._entries = proxies
        self._sessions = tuple(
            AiohttpSession(proxy=entry.url, api=api, timeout=timeout)
            for entry in proxies
        )
        self._cursor = 0

    @property
    def proxy_count(self) -> int:
        return len(self._entries)

    def _order(self) -> tuple[int, ...]:
        start = self._cursor % len(self._entries)
        self._cursor = (start + 1) % len(self._entries)
        return tuple(
            (start + offset) % len(self._entries)
            for offset in range(len(self._entries))
        )

    @staticmethod
    def _fields(entry: ProxyEntry, attempt: int) -> dict[str, object]:
        return {
            "proxy": entry.name,
            "proxy_scheme": entry.scheme,
            "proxy_attempt": attempt,
        }

    async def make_request(
        self,
        bot: Bot,
        method: TelegramMethod[TelegramType],
        timeout: int | None = None,
    ) -> TelegramType:
        last_error: TelegramNetworkError | TelegramServerError | None = None
        order = self._order()
        for attempt, index in enumerate(order, 1):
            entry = self._entries[index]
            try:
                return cast(
                    TelegramType,
                    await self._sessions[index].make_request(bot, method, timeout),
                )
            except (TelegramNetworkError, TelegramServerError) as exc:
                last_error = exc
                if attempt >= len(order):
                    raise
                logging.warning(
                    "Telegram proxy attempt failed; trying next proxy",
                    extra={
                        "event": "telegram_proxy_failover",
                        "outcome": "retry",
                        "error_type": type(exc).__name__,
                        **self._fields(entry, attempt),
                    },
                )
        if last_error is not None:  # pragma: no cover
            raise last_error
        raise RuntimeError("Telegram proxy pool had no route")  # pragma: no cover

    async def stream_content(
        self,
        url: str,
        headers: dict[str, Any] | None = None,
        timeout: int = 30,
        chunk_size: int = 65536,
        raise_for_status: bool = True,
    ) -> AsyncGenerator[bytes, None]:
        order = self._order()
        for attempt, index in enumerate(order, 1):
            entry = self._entries[index]
            yielded = False
            try:
                async for chunk in self._sessions[index].stream_content(
                    url,
                    headers=headers,
                    timeout=timeout,
                    chunk_size=chunk_size,
                    raise_for_status=raise_for_status,
                ):
                    yielded = True
                    yield chunk
                return
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                if yielded or attempt >= len(order):
                    raise
                logging.warning(
                    "Telegram proxy stream failed before data; trying next proxy",
                    extra={
                        "event": "telegram_proxy_failover",
                        "outcome": "retry",
                        "error_type": type(exc).__name__,
                        **self._fields(entry, attempt),
                    },
                )

    async def close(self) -> None:
        for session in self._sessions:
            await session.close()
