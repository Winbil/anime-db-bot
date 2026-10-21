from __future__ import annotations

import os

from aiogram import Bot
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer

from bots.telegram.transports import TelegramTransport


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


class LocalTelegramTransport(TelegramTransport):
    """Telegram transport backed by a self-hosted telegram-bot-api server."""

    key = "tgapi"
    mode_name = "local tg-bot-api"

    @property
    def api_url(self) -> str:
        value = os.getenv("TELEGRAM_BOT_API_URL", "").strip().rstrip("/")
        if not value:
            raise RuntimeError(
                "TELEGRAM_BOT_API_URL is empty, but the local tg-bot-api transport was selected."
            )
        return value

    @property
    def endpoint_label(self) -> str:
        return self.api_url

    @property
    def is_local(self) -> bool:
        return _env_bool("TELEGRAM_BOT_API_LOCAL", False)

    def create_bot(self) -> Bot:
        api = TelegramAPIServer.from_base(
            self.api_url,
            is_local=self.is_local,
        )
        session = AiohttpSession(api=api)
        return Bot(token=self.bot_token(), session=session)


TRANSPORT = LocalTelegramTransport()
