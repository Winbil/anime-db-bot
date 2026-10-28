from __future__ import annotations

from aiogram import Bot
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer

from bots.telegram.transports import TelegramTransport
from core.settings import get_settings


class LocalTelegramTransport(TelegramTransport):
    """Telegram transport backed by a self-hosted telegram-bot-api server."""

    key = "tgapi"
    mode_name = "local tg-bot-api"

    @property
    def api_url(self) -> str:
        value = get_settings().telegram.bot_api_url.rstrip("/")
        if not value:
            raise RuntimeError(
                "TELEGRAM_BOT_API_URL is empty, but the local tg-bot-api transport was selected."
            )
        return value

    @property
    def endpoint_label(self) -> str:
        return get_settings().telegram.bot_api_url.rstrip("/") or self.mode_name

    @property
    def is_local(self) -> bool:
        return get_settings().telegram.bot_api_local

    def create_bot(self) -> Bot:
        api = TelegramAPIServer.from_base(
            self.api_url,
            is_local=self.is_local,
        )
        session = AiohttpSession(api=api)
        return Bot(token=self.bot_token(), session=session)


TRANSPORT = LocalTelegramTransport()
