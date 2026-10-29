from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from bots.telegram.rate_limit import TelegramRateLimitMiddleware
from core.identity import AnimeIdentity
from core.people_loading import PeopleBatch
from services.runtime.rate_limits import PersonalRateLimiter, RateLimitDecision
from sources.runtime.rate_limited import (
    PeopleRateLimitedSourceProxy,
    RateLimitedSourceProxy,
)


class TelegramRateLimitMiddlewareTests(unittest.IsolatedAsyncioTestCase):
    async def test_admin_bypasses_only_personal_limiter(self) -> None:
        limiter = MagicMock(spec=PersonalRateLimiter)
        middleware = TelegramRateLimitMiddleware(limiter)
        handler = AsyncMock(return_value="ok")
        event = SimpleNamespace(from_user=SimpleNamespace(id=123))

        with patch("bots.telegram.rate_limit.is_telegram_admin", return_value=True):
            result = await middleware(handler, event, {})

        self.assertEqual(result, "ok")
        limiter.check.assert_not_called()
        handler.assert_awaited_once_with(event, {})

    async def test_regular_user_uses_platform_scoped_personal_bucket(self) -> None:
        limiter = MagicMock(spec=PersonalRateLimiter)
        limiter.check.return_value = RateLimitDecision(True)
        middleware = TelegramRateLimitMiddleware(limiter)
        handler = AsyncMock(return_value="ok")
        event = SimpleNamespace(from_user=SimpleNamespace(id=456))

        with patch("bots.telegram.rate_limit.is_telegram_admin", return_value=False):
            result = await middleware(handler, event, {})

        self.assertEqual(result, "ok")
        limiter.check.assert_called_once_with("telegram", 456)
        handler.assert_awaited_once_with(event, {})


class _MetadataSource:
    name = "AniList"

    def __init__(self) -> None:
        self.get_details = AsyncMock(return_value=None)


class _PeopleSource:
    name = "Shikimori"

    def __init__(self) -> None:
        self.load_characters = AsyncMock(return_value=[])
        self.load_staff = AsyncMock(return_value=[])
        self.load_voices = AsyncMock(return_value=[])
        self.load_staff_batch = AsyncMock(return_value=PeopleBatch(complete=True))
        self.load_voices_batch = AsyncMock(return_value=PeopleBatch(complete=True))
        self.load_screenshots = AsyncMock(return_value=[])


class RateLimitedSourceProxyTests(unittest.IsolatedAsyncioTestCase):
    async def test_metadata_proxy_waits_before_delegate(self) -> None:
        source = _MetadataSource()
        proxy = RateLimitedSourceProxy(source, "anilist")
        identity = AnimeIdentity.from_mapping({"anilist": "1"})

        with patch(
            "sources.runtime.rate_limited.wait_for_upstream", new=AsyncMock()
        ) as wait:
            await proxy.get_details(identity)

        wait.assert_awaited_once_with("anilist", "metadata")
        source.get_details.assert_awaited_once_with(identity)

    async def test_character_loader_uses_people_bucket(self) -> None:
        source = _PeopleSource()
        proxy = PeopleRateLimitedSourceProxy(source, "shikimori")
        identity = AnimeIdentity.from_mapping({"shikimori": "1"})

        with patch(
            "sources.runtime.rate_limited.wait_for_upstream", new=AsyncMock()
        ) as wait:
            await proxy.load_characters(identity)

        wait.assert_awaited_once_with("shikimori", "people")
        source.load_characters.assert_awaited_once_with(identity)

    async def test_lazy_metadata_capability_uses_metadata_bucket(self) -> None:
        source = _PeopleSource()
        proxy = PeopleRateLimitedSourceProxy(source, "shikimori")
        identity = AnimeIdentity.from_mapping({"shikimori": "1"})

        with patch(
            "sources.runtime.rate_limited.wait_for_upstream", new=AsyncMock()
        ) as wait:
            await proxy.load_screenshots(identity)

        wait.assert_awaited_once_with("shikimori", "metadata")
        source.load_screenshots.assert_awaited_once_with(identity)

    async def test_people_batch_proxy_preserves_portrait_limit(self) -> None:
        source = _PeopleSource()
        proxy = PeopleRateLimitedSourceProxy(source, "shikimori")
        identity = AnimeIdentity.from_mapping({"shikimori": "1"})

        with patch(
            "sources.runtime.rate_limited.wait_for_upstream", new=AsyncMock()
        ) as wait:
            await proxy.load_voices_batch(
                identity,
                cursor="8",
                portrait_limit=50,
            )

        wait.assert_awaited_once_with("shikimori", "people")
        source.load_voices_batch.assert_awaited_once_with(
            identity,
            cursor="8",
            portrait_limit=50,
        )


if __name__ == "__main__":
    unittest.main()
