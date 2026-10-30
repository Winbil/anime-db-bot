from __future__ import annotations

from aiogram import Bot

from bots.telegram.transports import TelegramTransport
from bots.telegram.transports.proxy_session import (
    ProxyPoolAiohttpSession,
    UserAgentPoolAiohttpSession,
)


class OfficialTelegramTransport(TelegramTransport):
    """Telegram transport backed by the official api.telegram.org endpoint."""

    key = "official"
    mode_name = "official api.telegram.org"

    @property
    def endpoint_label(self) -> str:
        return "https://api.telegram.org"

    def create_bot(self) -> Bot:
        proxies = self.proxy_profile.active
        user_agents = self.user_agent_profile.preferred
        session = (
            ProxyPoolAiohttpSession(proxies, user_agents=user_agents)
            if proxies
            else UserAgentPoolAiohttpSession(user_agents)
        )
        return Bot(token=self.bot_token(), session=session)
