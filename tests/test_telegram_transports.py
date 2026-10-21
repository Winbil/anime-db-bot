from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from bots.telegram.transports.official import TRANSPORT as OFFICIAL_TRANSPORT
from bots.telegram.transports.tgapi import TRANSPORT as TGAPI_TRANSPORT


class TelegramTransportCreationTests(unittest.TestCase):
    def test_official_transport_creates_default_aiogram_bot(self) -> None:
        bot_object = object()
        with (
            patch.dict("os.environ", {"BOT_TOKEN": "123456:TEST_TOKEN"}, clear=True),
            patch("bots.telegram.transports.official.Bot", return_value=bot_object) as bot_cls,
        ):
            self.assertIs(OFFICIAL_TRANSPORT.create_bot(), bot_object)

        bot_cls.assert_called_once_with(token="123456:TEST_TOKEN")

    def test_local_transport_creates_custom_api_session(self) -> None:
        api_object = object()
        session_object = object()
        bot_object = object()
        env = {
            "BOT_TOKEN": "123456:TEST_TOKEN",
            "TELEGRAM_BOT_API_URL": "http://127.0.0.1:8081/",
            "TELEGRAM_BOT_API_LOCAL": "true",
        }
        with (
            patch.dict("os.environ", env, clear=True),
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
            self.assertIs(TGAPI_TRANSPORT.create_bot(), bot_object)

        from_base.assert_called_once_with(
            "http://127.0.0.1:8081",
            is_local=True,
        )
        session_cls.assert_called_once_with(api=api_object)
        bot_cls.assert_called_once_with(
            token="123456:TEST_TOKEN",
            session=session_object,
        )


class TelegramTransportLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def test_health_probe_returns_bot_identity(self) -> None:
        bot = SimpleNamespace(
            get_me=AsyncMock(return_value=SimpleNamespace(username="anime_test_bot")),
            session=SimpleNamespace(close=AsyncMock()),
        )

        health = await OFFICIAL_TRANSPORT.check_health(bot)

        self.assertTrue(health.healthy)
        self.assertEqual(health.bot_username, "anime_test_bot")
        self.assertIn("getMe", health.detail)

        await OFFICIAL_TRANSPORT.close(bot)
        bot.session.close.assert_awaited_once()

    async def test_health_probe_reports_backend_failure(self) -> None:
        bot = SimpleNamespace(
            get_me=AsyncMock(side_effect=RuntimeError("backend unavailable")),
            session=SimpleNamespace(close=AsyncMock()),
        )

        health = await TGAPI_TRANSPORT.check_health(bot)

        self.assertFalse(health.healthy)
        self.assertIn("backend unavailable", health.detail)


if __name__ == "__main__":
    unittest.main()
