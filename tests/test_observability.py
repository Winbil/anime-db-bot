from __future__ import annotations

import io
import json
import logging
import unittest
from unittest.mock import patch

import httpx

from core.cache import BoundedTTLCache
from core.http_client import HttpClientPool
from core.logging_config import (
    SecretRedactor,
    StructuredLogFormatter,
    configure_logging,
)
from core.observability import bind_observability_context, current_observability_context


class ObservabilityContextTests(unittest.TestCase):
    def test_structured_logs_inherit_privacy_safe_context(self) -> None:
        stream = io.StringIO()
        logger = logging.getLogger("anime-db-bot-observability-context")
        logger.propagate = False
        configure_logging(structured=True, stream=stream, logger=logger)

        with bind_observability_context(
            correlation_id="corr-123",
            platform="telegram",
            action="command",
        ):
            logger.info(
                "Update accepted",
                extra={"event": "telegram_update", "outcome": "started"},
            )

        payload = json.loads(stream.getvalue())
        self.assertEqual(payload["correlation_id"], "corr-123")
        self.assertEqual(payload["platform"], "telegram")
        self.assertEqual(payload["action"], "command")
        self.assertEqual(payload["event"], "telegram_update")
        self.assertEqual(payload["outcome"], "started")
        self.assertIsNone(current_observability_context().correlation_id)

    def test_nested_context_restores_parent_values(self) -> None:
        with bind_observability_context(
            correlation_id="outer",
            platform="telegram",
            action="message",
        ):
            with bind_observability_context(action="callback"):
                current = current_observability_context()
                self.assertEqual(current.correlation_id, "outer")
                self.assertEqual(current.action, "callback")
            self.assertEqual(current_observability_context().action, "message")

    def test_proxy_url_passwords_are_redacted_for_http_and_socks(self) -> None:
        redactor = SecretRedactor()
        for url in (
            "http://proxy-user:proxy-pass@example.invalid:8080",
            "socks4://proxy-user:proxy-pass@example.invalid:1080",
            "socks5h://proxy-user:proxy-pass@example.invalid:1080",
        ):
            redacted = redactor.redact(url)
            self.assertNotIn("proxy-pass", redacted)
            self.assertIn("<redacted>", redacted)


class _FakeAsyncClient:
    async def request(self, method: str, url: str, **kwargs: object) -> httpx.Response:
        return httpx.Response(200, request=httpx.Request(method, url))


class ObservabilityPrivacyTests(unittest.IsolatedAsyncioTestCase):
    async def test_http_event_propagates_context_without_logging_raw_url(self) -> None:
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(StructuredLogFormatter(SecretRedactor()))
        root = logging.getLogger()
        old_level = root.level
        root.addHandler(handler)
        root.setLevel(logging.INFO)
        pool = HttpClientPool()
        try:
            with patch.object(pool, "_client", return_value=_FakeAsyncClient()):
                with bind_observability_context(
                    correlation_id="http-corr",
                    platform="telegram",
                    action="command",
                ):
                    response = await pool.request(
                        "anilist",
                        "GET",
                        "https://example.invalid/private/path?query=secret-title",
                        operation="metadata",
                    )
            self.assertEqual(response.status_code, 200)
        finally:
            root.removeHandler(handler)
            root.setLevel(old_level)

        payload = json.loads(stream.getvalue())
        self.assertEqual(payload["event"], "source_http_request")
        self.assertEqual(payload["source"], "anilist")
        self.assertEqual(payload["operation"], "metadata")
        self.assertEqual(payload["correlation_id"], "http-corr")
        self.assertEqual(payload["outcome"], "success")
        self.assertEqual(payload["status_code"], 200)
        self.assertNotIn("example.invalid", stream.getvalue())
        self.assertNotIn("secret-title", stream.getvalue())

    async def test_cache_eviction_does_not_log_cache_keys(self) -> None:
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(StructuredLogFormatter(SecretRedactor()))
        root = logging.getLogger()
        old_level = root.level
        root.addHandler(handler)
        root.setLevel(logging.INFO)
        try:
            cache = BoundedTTLCache[str, str](
                max_entries=1,
                ttl_seconds=60,
                name="privacy_test",
            )
            cache.set("private-query-title", "first")
            cache.set("another-private-key", "second")
        finally:
            root.removeHandler(handler)
            root.setLevel(old_level)

        payload = json.loads(stream.getvalue())
        self.assertEqual(payload["event"], "cache_eviction")
        self.assertEqual(payload["cache"], "privacy_test")
        self.assertEqual(payload["evicted"], 1)
        self.assertNotIn("private-query-title", stream.getvalue())
        self.assertNotIn("another-private-key", stream.getvalue())


if __name__ == "__main__":
    unittest.main()
