from __future__ import annotations

import os
import unittest
from unittest.mock import AsyncMock, patch

from services.rate_limits import (
    PersonalRateLimiter,
    UpstreamRateLimiter,
    _operation_limit,
    _source_limit,
)


class PersonalRateLimiterTests(unittest.TestCase):
    def test_minute_limit_is_scoped_per_user(self) -> None:
        limiter = PersonalRateLimiter()
        with patch.dict(
            os.environ,
            {
                "USER_RATE_LIMIT_PER_MINUTE": "2",
                "USER_RATE_LIMIT_PER_HOUR": "100",
            },
            clear=False,
        ):
            self.assertTrue(limiter.check("telegram", 100, now=0).allowed)
            self.assertTrue(limiter.check("telegram", 100, now=1).allowed)

            blocked = limiter.check("telegram", 100, now=2)
            self.assertFalse(blocked.allowed)
            self.assertEqual(blocked.window, "minute")
            self.assertEqual(blocked.retry_after, 58)

            # A different account has a completely independent bucket.
            self.assertTrue(limiter.check("telegram", 200, now=2).allowed)

    def test_platform_is_part_of_personal_bucket_key(self) -> None:
        limiter = PersonalRateLimiter()
        with patch.dict(
            os.environ,
            {
                "USER_RATE_LIMIT_PER_MINUTE": "1",
                "USER_RATE_LIMIT_PER_HOUR": "100",
            },
            clear=False,
        ):
            self.assertTrue(limiter.check("telegram", 100, now=0).allowed)
            self.assertFalse(limiter.check("telegram", 100, now=1).allowed)
            self.assertTrue(limiter.check("discord", 100, now=1).allowed)

    def test_hour_limit_is_independent_from_minute_limit(self) -> None:
        limiter = PersonalRateLimiter()
        with patch.dict(
            os.environ,
            {
                "USER_RATE_LIMIT_PER_MINUTE": "100",
                "USER_RATE_LIMIT_PER_HOUR": "2",
            },
            clear=False,
        ):
            self.assertTrue(limiter.check("telegram", 100, now=0).allowed)
            self.assertTrue(limiter.check("telegram", 100, now=61).allowed)

            blocked = limiter.check("telegram", 100, now=62)
            self.assertFalse(blocked.allowed)
            self.assertEqual(blocked.window, "hour")
            self.assertEqual(blocked.retry_after, 3538)

    def test_blocked_attempt_is_not_added_to_bucket(self) -> None:
        limiter = PersonalRateLimiter()
        with patch.dict(
            os.environ,
            {
                "USER_RATE_LIMIT_PER_MINUTE": "1",
                "USER_RATE_LIMIT_PER_HOUR": "100",
            },
            clear=False,
        ):
            self.assertTrue(limiter.check("telegram", 100, now=0).allowed)
            self.assertFalse(limiter.check("telegram", 100, now=1).allowed)
            self.assertFalse(limiter.check("telegram", 100, now=30).allowed)
            self.assertTrue(limiter.check("telegram", 100, now=61).allowed)


class UpstreamRateLimiterTests(unittest.IsolatedAsyncioTestCase):
    def test_source_specific_configuration_has_priority(self) -> None:
        with patch.dict(
            os.environ,
            {
                "UPSTREAM_RATE_LIMIT_DEFAULT_PER_MINUTE": "999",
                "UPSTREAM_RATE_LIMIT_ANILIST_PER_MINUTE": "77",
                "UPSTREAM_RATE_LIMIT_ANILIST_PEOPLE_PER_MINUTE": "13",
            },
            clear=False,
        ):
            self.assertEqual(_source_limit("anilist"), 77)
            self.assertEqual(_operation_limit("anilist", "people"), 13)

    def test_builtin_source_defaults_are_conservative(self) -> None:
        keys = [
            "UPSTREAM_RATE_LIMIT_DEFAULT_PER_MINUTE",
            "UPSTREAM_RATE_LIMIT_ANILIST_PER_MINUTE",
            "UPSTREAM_RATE_LIMIT_SHIKIMORI_PER_MINUTE",
            "UPSTREAM_RATE_LIMIT_MAL_PER_MINUTE",
        ]
        with patch.dict(os.environ, {}, clear=False):
            previous = {key: os.environ.pop(key, None) for key in keys}
            try:
                self.assertEqual(_source_limit("anilist"), 80)
                self.assertEqual(_source_limit("shikimori"), 240)
                self.assertEqual(_source_limit("mal"), 120)
            finally:
                for key, value in previous.items():
                    if value is not None:
                        os.environ[key] = value

    async def test_people_operation_uses_source_and_endpoint_buckets(self) -> None:
        limiter = UpstreamRateLimiter()
        limiter._acquire_bucket = AsyncMock()  # type: ignore[method-assign]

        with patch.dict(
            os.environ,
            {
                "UPSTREAM_RATE_LIMIT_ANILIST_PER_MINUTE": "80",
                "UPSTREAM_RATE_LIMIT_ANILIST_PEOPLE_PER_MINUTE": "20",
            },
            clear=False,
        ):
            await limiter.acquire("anilist", "people")

        self.assertEqual(limiter._acquire_bucket.await_count, 2)
        limiter._acquire_bucket.assert_any_await(("source", "anilist"), 80)
        limiter._acquire_bucket.assert_any_await(
            ("operation", "anilist", "people"),
            20,
        )

    async def test_regular_operation_still_consumes_source_bucket(self) -> None:
        limiter = UpstreamRateLimiter()
        limiter._acquire_bucket = AsyncMock()  # type: ignore[method-assign]

        with patch.dict(
            os.environ,
            {"UPSTREAM_RATE_LIMIT_MAL_PER_MINUTE": "120"},
            clear=False,
        ):
            await limiter.acquire("mal", "metadata")

        limiter._acquire_bucket.assert_awaited_once_with(("source", "mal"), 120)


if __name__ == "__main__":
    unittest.main()
