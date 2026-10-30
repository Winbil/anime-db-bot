from __future__ import annotations

from aiogram import Bot
from aiogram.client.telegram import TelegramAPIServer

from bots.telegram.transports import TelegramTransport
from bots.telegram.transports.proxy_session import UserAgentPoolAiohttpSession


class LocalTelegramTransport(TelegramTransport):
    """Telegram transport backed by a self-hosted telegram-bot-api server."""

    key = "tgapi"
    mode_name = "local tg-bot-api"

    @property
    def api_url(self) -> str:
        value = self.settings.bot_api_url.rstrip("/")
        if not value:
            raise RuntimeError(
                "TELEGRAM_BOT_API_URL is empty, but the local tg-bot-api transport was selected."
            )
        return value

    @property
    def endpoint_label(self) -> str:
        return self.settings.bot_api_url.rstrip("/") or self.mode_name

    @property
    def is_local(self) -> bool:
        return self.settings.bot_api_local

    def create_bot(self) -> Bot:
        api = TelegramAPIServer.from_base(
            self.api_url,
            is_local=self.is_local,
        )
        session = UserAgentPoolAiohttpSession(
            self.user_agent_profile.preferred,
            api=api,
        )
        return Bot(token=self.bot_token(), session=session)
