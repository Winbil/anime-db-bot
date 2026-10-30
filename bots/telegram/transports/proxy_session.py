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

from core.http_config import USER_AGENT
from core.proxy_config import ProxyEntry
from core.user_agent_config import UserAgentEntry

TelegramType = TypeVar("TelegramType")


class _NamedUserAgentSession(AiohttpSession):
    """AiohttpSession with an explicit User-Agent header."""

    def __init__(self, user_agent: str, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._configured_user_agent = user_agent

    async def create_session(self):
        session = await super().create_session()
        session.headers["User-Agent"] = self._configured_user_agent
        return session


def _effective_user_agents(
    entries: tuple[UserAgentEntry, ...],
) -> tuple[UserAgentEntry, ...]:
    if entries:
        top = max(entry.priority for entry in entries)
        preferred = tuple(entry for entry in entries if entry.priority == top)
        if preferred:
            return preferred
    return (UserAgentEntry(name="default", value=USER_AGENT, priority=0),)


class UserAgentPoolAiohttpSession(BaseSession):
    """Direct aiogram session rotating User-Agents within the top priority tier."""

    def __init__(
        self,
        user_agents: tuple[UserAgentEntry, ...] = (),
        *,
        api: TelegramAPIServer = PRODUCTION,
        timeout: float = 60.0,
    ) -> None:
        super().__init__(api=api, timeout=timeout)
        self._entries = _effective_user_agents(user_agents)
        self._sessions = tuple(
            _NamedUserAgentSession(entry.value, api=api, timeout=timeout)
            for entry in self._entries
        )
        self._cursor = 0

    def _index(self) -> int:
        index = self._cursor % len(self._sessions)
        self._cursor = (index + 1) % len(self._sessions)
        return index

    async def make_request(
        self,
        bot: Bot,
        method: TelegramMethod[TelegramType],
        timeout: int | None = None,
    ) -> TelegramType:
        return cast(
            TelegramType,
            await self._sessions[self._index()].make_request(bot, method, timeout),
        )

    async def stream_content(
        self,
        url: str,
        headers: dict[str, Any] | None = None,
        timeout: int = 30,
        chunk_size: int = 65536,
        raise_for_status: bool = True,
    ) -> AsyncGenerator[bytes, None]:
        async for chunk in self._sessions[self._index()].stream_content(
            url,
            headers=headers,
            timeout=timeout,
            chunk_size=chunk_size,
            raise_for_status=raise_for_status,
        ):
            yield chunk

    async def close(self) -> None:
        for session in self._sessions:
            await session.close()


class ProxyPoolAiohttpSession(BaseSession):
    """Aiogram session with prioritized proxy failover and User-Agent selection."""

    def __init__(
        self,
        proxies: tuple[ProxyEntry, ...],
        *,
        user_agents: tuple[UserAgentEntry, ...] = (),
        api: TelegramAPIServer = PRODUCTION,
        timeout: float = 60.0,
    ) -> None:
        if not proxies:
            raise ValueError("ProxyPoolAiohttpSession requires at least one proxy")
        super().__init__(api=api, timeout=timeout)
        self._entries = proxies
        self._user_agents = _effective_user_agents(user_agents)
        self._sessions = tuple(
            tuple(
                _NamedUserAgentSession(
                    user_agent.value,
                    proxy=proxy.url,
                    api=api,
                    timeout=timeout,
                )
                for user_agent in self._user_agents
            )
            for proxy in proxies
        )
        self._proxy_cursor: dict[int, int] = {}
        self._user_agent_cursor = 0

    @property
    def proxy_count(self) -> int:
        return len(self._entries)

    def _order(self) -> tuple[int, ...]:
        ordered: list[int] = []
        for priority in sorted(
            {entry.priority for entry in self._entries}, reverse=True
        ):
            tier = tuple(
                index
                for index, entry in enumerate(self._entries)
                if entry.priority == priority
            )
            start = self._proxy_cursor.get(priority, 0) % len(tier)
            self._proxy_cursor[priority] = (start + 1) % len(tier)
            ordered.extend(
                tier[(start + offset) % len(tier)] for offset in range(len(tier))
            )
        return tuple(ordered)

    def _user_agent_index(self) -> int:
        index = self._user_agent_cursor % len(self._user_agents)
        self._user_agent_cursor = (index + 1) % len(self._user_agents)
        return index

    @staticmethod
    def _fields(entry: ProxyEntry, attempt: int) -> dict[str, object]:
        return {
            "proxy": entry.name,
            "proxy_scheme": entry.scheme,
            "proxy_priority": entry.priority,
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
        user_agent_index = self._user_agent_index()
        for attempt, index in enumerate(order, 1):
            entry = self._entries[index]
            try:
                return cast(
                    TelegramType,
                    await self._sessions[index][user_agent_index].make_request(
                        bot, method, timeout
                    ),
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
        user_agent_index = self._user_agent_index()
        for attempt, index in enumerate(order, 1):
            entry = self._entries[index]
            yielded = False
            try:
                async for chunk in self._sessions[index][
                    user_agent_index
                ].stream_content(
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
        for sessions in self._sessions:
            for session in sessions:
                await session.close()
