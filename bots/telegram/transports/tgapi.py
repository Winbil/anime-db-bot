from __future__ import annotations

from bots.telegram.transports import TelegramTransport


TRANSPORT = TelegramTransport(
    key="tgapi",
    mode_name="local tg-bot-api",
    use_custom_api=True,
)
