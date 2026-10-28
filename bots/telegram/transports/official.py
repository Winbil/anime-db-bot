from __future__ import annotations

from aiogram import Bot

from bots.telegram.transports import TelegramTransport


class OfficialTelegramTransport(TelegramTransport):
    """Telegram transport backed by the official api.telegram.org endpoint."""

    key = "official"
    mode_name = "official api.telegram.org"

    @property
    def endpoint_label(self) -> str:
        return "https://api.telegram.org"

    def create_bot(self) -> Bot:
        return Bot(token=self.bot_token())
