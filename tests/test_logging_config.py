from __future__ import annotations

import io
import json
import logging
import unittest
from datetime import datetime

from core.logging_config import SecretRedactor, configure_logging


class LoggingConfigTests(unittest.TestCase):
    def test_redactor_removes_explicit_and_common_secret_shapes(self) -> None:
        redactor = SecretRedactor(["explicit-secret-value"])
        value = redactor.redact(
            "explicit-secret-value "
            "Bearer bearer.payload.value "
            "token=plain-token "
            "{'client_secret': 'dict-secret', 'cookie': 'session-secret'} "
            "https://user:pass123@example.invalid/path?access_token=query-token "
            "123456789:abcdefghijklmnopqrstuvwxyzABCDE"
        )
        self.assertNotIn("explicit-secret-value", value)
        self.assertNotIn("bearer.payload.value", value)
        self.assertNotIn("plain-token", value)
        self.assertNotIn("dict-secret", value)
        self.assertNotIn("session-secret", value)
        self.assertNotIn("pass123", value)
        self.assertNotIn("query-token", value)
        self.assertNotIn("abcdefghijklmnopqrstuvwxyzABCDE", value)
        self.assertGreaterEqual(value.count("<redacted>"), 8)

    def test_structured_logging_emits_json_and_redacts_exception_text(self) -> None:
        stream = io.StringIO()
        logger = logging.getLogger("anime-db-bot-test-structured")
        logger.propagate = False
        configure_logging(
            level="DEBUG",
            structured=True,
            secrets=["secret-value"],
            stream=stream,
            logger=logger,
        )
        try:
            raise RuntimeError("failed with secret-value")
        except RuntimeError:
            logger.exception(
                "request failed: %s",
                "secret-value",
                extra={"event": "source_failure", "source": "anilist"},
            )

        payload = json.loads(stream.getvalue())
        self.assertEqual(payload["level"], "ERROR")
        self.assertEqual(payload["logger"], logger.name)
        self.assertEqual(payload["event"], "source_failure")
        self.assertEqual(payload["source"], "anilist")
        self.assertNotIn("secret-value", payload["message"])
        self.assertNotIn("secret-value", payload["exception"])
        self.assertIn("<redacted>", payload["message"])
        self.assertIn("RuntimeError", payload["exception"])

    def test_text_logging_uses_same_redactor(self) -> None:
        stream = io.StringIO()
        logger = logging.getLogger("anime-db-bot-test-text")
        logger.propagate = False
        configure_logging(
            structured=False,
            secrets=["secret-value"],
            stream=stream,
            logger=logger,
        )
        logger.warning("Authorization: Bearer secret-value")
        output = stream.getvalue()
        self.assertIn("WARNING", output)
        self.assertNotIn("secret-value", output)
        self.assertIn("<redacted>", output)

    def test_redaction_can_be_explicitly_disabled(self) -> None:
        stream = io.StringIO()
        logger = logging.getLogger("anime-db-bot-test-unredacted")
        logger.propagate = False
        configure_logging(
            structured=True,
            secrets=["secret-value"],
            redact_secrets=False,
            stream=stream,
            logger=logger,
        )
        logger.warning(
            "Authorization: Bearer secret-value token=plain-token "
            "https://user:pass@example.invalid/?access_token=query-token"
        )
        payload = json.loads(stream.getvalue())
        self.assertIn("secret-value", payload["message"])
        self.assertIn("plain-token", payload["message"])
        self.assertIn("pass", payload["message"])
        self.assertIn("query-token", payload["message"])
        self.assertNotIn("<redacted>", payload["message"])

    def test_structured_timestamp_uses_runtime_local_timezone(self) -> None:
        stream = io.StringIO()
        logger = logging.getLogger("anime-db-bot-test-local-time")
        logger.propagate = False
        configure_logging(structured=True, stream=stream, logger=logger)
        logger.info("timezone check")

        payload = json.loads(stream.getvalue())
        timestamp = datetime.fromisoformat(payload["timestamp"])
        self.assertIsNotNone(timestamp.utcoffset())
        expected = datetime.fromtimestamp(timestamp.timestamp()).astimezone()
        self.assertEqual(timestamp.utcoffset(), expected.utcoffset())
        self.assertEqual(payload["timezone"], expected.tzname())

    def test_text_timestamp_includes_runtime_local_offset(self) -> None:
        stream = io.StringIO()
        logger = logging.getLogger("anime-db-bot-test-text-local-time")
        logger.propagate = False
        configure_logging(structured=False, stream=stream, logger=logger)
        logger.info("timezone check")
        prefix = stream.getvalue().split(" | ", 1)[0]
        timestamp = datetime.fromisoformat(prefix)
        self.assertIsNotNone(timestamp.utcoffset())


if __name__ == "__main__":
    unittest.main()
