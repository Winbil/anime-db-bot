from __future__ import annotations

from dataclasses import dataclass

from aiogram import Bot

from core.settings import TelegramSettings


@dataclass(frozen=True, slots=True)
class TransportHealth:
    """Current health of a Telegram Bot API transport."""

    healthy: bool
    detail: str
    bot_username: str | None = None


class TelegramTransport:
    """Backend boundary between the bot runtime and a Telegram Bot API server."""

    key = "base"
    mode_name = "Telegram Bot API"

    def __init__(self, settings: TelegramSettings) -> None:
        self._settings = settings

    @property
    def settings(self) -> TelegramSettings:
        return self._settings

    @property
    def endpoint_label(self) -> str:
        return self.mode_name

    def bot_token(self) -> str:
        token = self._settings.bot_token
        if not token:
            raise RuntimeError(
                "BOT_TOKEN is not set. Copy .env.example to .env and add the bot token."
            )
        return token

    def create_bot(self) -> Bot:
        """Create an aiogram Bot configured for this transport backend."""
        raise NotImplementedError

    async def check_health(self, bot: Bot) -> TransportHealth:
        """Probe the selected Bot API backend through Telegram getMe."""
        try:
            me = await bot.get_me()
        except Exception as exc:
            return TransportHealth(
                healthy=False,
                detail=(
                    f"{self.endpoint_label} did not answer getMe: "
                    f"{type(exc).__name__}: {exc}"
                ),
            )

        username = getattr(me, "username", None)
        return TransportHealth(
            healthy=True,
            detail=f"{self.endpoint_label} answered getMe successfully.",
            bot_username=username,
        )

    async def close(self, bot: Bot) -> None:
        """Release transport-owned HTTP resources."""
        await bot.session.close()
