from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from bots.telegram.transports.official import OfficialTelegramTransport
from bots.telegram.transports.tgapi import LocalTelegramTransport
from core.settings import TelegramSettings


def telegram_settings(
    *,
    bot_token: str = "123456:TEST_TOKEN",
    bot_api_url: str = "",
    bot_api_local: bool = False,
) -> TelegramSettings:
    return TelegramSettings(
        bot_token=bot_token,
        bot_api_url=bot_api_url,
        bot_api_local=bot_api_local,
        session_ttl_seconds=3600,
        anime_input_ttl_seconds=300,
        admin_user_ids=(),
    )


class TelegramTransportCreationTests(unittest.TestCase):
    def test_official_transport_creates_default_aiogram_bot(self) -> None:
        bot_object = object()
        transport = OfficialTelegramTransport(telegram_settings())
        with patch(
            "bots.telegram.transports.official.Bot", return_value=bot_object
        ) as bot_cls:
            self.assertIs(transport.create_bot(), bot_object)

        bot_cls.assert_called_once_with(token="123456:TEST_TOKEN")

    def test_local_transport_creates_custom_api_session(self) -> None:
        api_object = object()
        session_object = object()
        bot_object = object()
        transport = LocalTelegramTransport(
            telegram_settings(
                bot_api_url="http://127.0.0.1:8081/",
                bot_api_local=True,
            )
        )
        with (
            patch(
                "bots.telegram.transports.tgapi.TelegramAPIServer.from_base",
                return_value=api_object,
            ) as from_base,
            patch(
                "bots.telegram.transports.tgapi.AiohttpSession",
                return_value=session_object,
            ) as session_cls,
            patch(
                "bots.telegram.transports.tgapi.Bot",
                return_value=bot_object,
            ) as bot_cls,
        ):
            self.assertIs(transport.create_bot(), bot_object)

        from_base.assert_called_once_with(
            "http://127.0.0.1:8081",
            is_local=True,
        )
        session_cls.assert_called_once_with(api=api_object)
        bot_cls.assert_called_once_with(
            token="123456:TEST_TOKEN",
            session=session_object,
        )

    def test_transport_uses_frozen_settings_not_environment(self) -> None:
        transport = LocalTelegramTransport(
            telegram_settings(
                bot_token="123456:FROZEN_TOKEN",
                bot_api_url="http://127.0.0.1:9000/",
                bot_api_local=True,
            )
        )
        with patch.dict(
            "os.environ",
            {
                "BOT_TOKEN": "999999:CHANGED",
                "TELEGRAM_BOT_API_URL": "http://127.0.0.1:7777",
                "TELEGRAM_BOT_API_LOCAL": "false",
            },
            clear=True,
        ):
            self.assertEqual(transport.bot_token(), "123456:FROZEN_TOKEN")
            self.assertEqual(transport.api_url, "http://127.0.0.1:9000")
            self.assertTrue(transport.is_local)


class TelegramTransportLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def test_health_probe_returns_bot_identity(self) -> None:
        transport = OfficialTelegramTransport(telegram_settings())
        bot = SimpleNamespace(
            get_me=AsyncMock(return_value=SimpleNamespace(username="anime_test_bot")),
            session=SimpleNamespace(close=AsyncMock()),
        )

        health = await transport.check_health(bot)

        self.assertTrue(health.healthy)
        self.assertEqual(health.bot_username, "anime_test_bot")
        self.assertIn("getMe", health.detail)

        await transport.close(bot)
        bot.session.close.assert_awaited_once()

    async def test_health_probe_reports_backend_failure(self) -> None:
        transport = LocalTelegramTransport(
            telegram_settings(bot_api_url="http://127.0.0.1:8081")
        )
        bot = SimpleNamespace(
            get_me=AsyncMock(side_effect=RuntimeError("backend unavailable")),
            session=SimpleNamespace(close=AsyncMock()),
        )

        health = await transport.check_health(bot)

        self.assertFalse(health.healthy)
        self.assertIn("backend unavailable", health.detail)


if __name__ == "__main__":
    unittest.main()
