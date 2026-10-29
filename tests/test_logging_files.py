from __future__ import annotations

import json
import logging
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from core.logging_config import (
    SecretRedactor,
    StructuredLogFormatter,
    configure_logging,
)
from core.logging_files import DailySplitFileHandler, classify_log_stream


class SplitLogFileTests(unittest.TestCase):
    def test_stream_classification(self) -> None:
        bot = logging.LogRecord("x", logging.INFO, __file__, 1, "bot", (), None)
        user = logging.LogRecord("x", logging.INFO, __file__, 1, "user", (), None)
        user.event = "telegram_update"
        api = logging.LogRecord("x", logging.INFO, __file__, 1, "api", (), None)
        api.event = "source_http_request"
        explicit = logging.LogRecord(
            "x", logging.INFO, __file__, 1, "explicit", (), None
        )
        explicit.log_stream = "users"

        self.assertEqual(classify_log_stream(bot), "bot")
        self.assertEqual(classify_log_stream(user), "users")
        self.assertEqual(classify_log_stream(api), "api")
        self.assertEqual(classify_log_stream(explicit), "users")

    def test_configured_logger_splits_bot_user_api_and_error_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            logger = logging.getLogger("anime-db-bot-test-split-files")
            logger.propagate = False
            configure_logging(
                structured=True,
                secrets=["secret-value"],
                log_directory=root,
                stream=None,
                logger=logger,
            )

            logger.info("runtime started")
            logger.info(
                "user action secret-value",
                extra={
                    "event": "telegram_update",
                    "outcome": "success",
                    "correlation_id": "corr-user",
                },
            )
            logger.info(
                "api request secret-value",
                extra={"event": "source_http_request", "source": "anilist"},
            )
            logger.error(
                "api failed secret-value",
                extra={"event": "source_call", "source": "anilist"},
            )

            day = datetime.now().astimezone().strftime("%Y.%m.%d")
            day_dir = root / day
            bot_lines = self._read_json_lines(day_dir / "bot.log")
            user_lines = self._read_json_lines(day_dir / "users.log")
            api_lines = self._read_json_lines(day_dir / "api.log")
            error_lines = self._read_json_lines(day_dir / "errors.log")

            self.assertEqual(len(bot_lines), 1)
            self.assertEqual(bot_lines[0]["log_stream"], "bot")
            self.assertEqual(len(user_lines), 1)
            self.assertEqual(user_lines[0]["log_stream"], "users")
            self.assertEqual(user_lines[0]["correlation_id"], "corr-user")
            self.assertEqual(len(api_lines), 2)
            self.assertTrue(all(line["log_stream"] == "api" for line in api_lines))
            self.assertEqual(len(error_lines), 1)
            self.assertEqual(error_lines[0]["level"], "ERROR")

            for path in (
                day_dir / "users.log",
                day_dir / "api.log",
                day_dir / "errors.log",
            ):
                self.assertNotIn("secret-value", path.read_text(encoding="utf-8"))

    def test_handler_rolls_to_new_daily_folder_without_restart(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            handler = DailySplitFileHandler(root)
            handler.setFormatter(StructuredLogFormatter(SecretRedactor()))

            first_time = (
                datetime.now().astimezone().replace(hour=23, minute=59, second=59)
            )
            second_time = first_time + timedelta(days=1, seconds=2)
            first = logging.LogRecord(
                "x", logging.INFO, __file__, 1, "before", (), None
            )
            second = logging.LogRecord(
                "x", logging.INFO, __file__, 1, "after", (), None
            )
            first.created = first_time.timestamp()
            second.created = second_time.timestamp()

            handler.emit(first)
            handler.emit(second)

            first_day = first_time.strftime("%Y.%m.%d")
            second_day = second_time.strftime("%Y.%m.%d")
            self.assertNotEqual(first_day, second_day)
            self.assertTrue((root / first_day / "bot.log").exists())
            self.assertTrue((root / second_day / "bot.log").exists())

    def test_size_rotation_is_per_individual_stream_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            logger = logging.getLogger("anime-db-bot-test-split-rotation")
            logger.propagate = False
            configure_logging(
                structured=False,
                log_directory=root,
                log_max_bytes=100,
                log_backups=2,
                logger=logger,
            )
            logger.info("A" * 80)
            logger.info("B" * 80)
            logger.info(
                "C" * 80,
                extra={"event": "source_http_request", "source": "test"},
            )

            day = datetime.now().astimezone().strftime("%Y.%m.%d")
            day_dir = root / day
            self.assertTrue((day_dir / "bot.log").exists())
            self.assertTrue((day_dir / "bot.log.1").exists())
            self.assertTrue((day_dir / "api.log").exists())
            self.assertFalse((day_dir / "api.log.1").exists())

    @staticmethod
    def _read_json_lines(path: Path) -> list[dict[str, object]]:
        return [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]


if __name__ == "__main__":
    unittest.main()
