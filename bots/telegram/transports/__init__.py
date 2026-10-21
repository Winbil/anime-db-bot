from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TelegramTransport:
    """Configuration that chooses which Telegram Bot API endpoint is used."""

    key: str
    mode_name: str
    use_custom_api: bool
