from __future__ import annotations

from bots.telegram.transports import TelegramTransport


TRANSPORT = TelegramTransport(
    key="official",
    mode_name="official api.telegram.org",
    use_custom_api=False,
)
