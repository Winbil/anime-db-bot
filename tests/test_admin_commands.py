from __future__ import annotations

import re
import sqlite3
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from aiogram import Bot, Dispatcher
from aiogram.types import Chat, Message, Update, User

from bots.telegram.admin import (
    _chunk_lines,
    _chunk_user_ids,
    _mapping_history_line,
    _mapping_override_line,
    _parse_ban_arguments,
    _parse_mapping_delete,
    _parse_mapping_history_limit,
    _parse_mapping_set,
    register_admin_handlers,
)
from mappings.resolver import MappingOverride, MappingOverrideHistory


class AdminCommandTests(unittest.TestCase):
    def test_permanent_ban_without_optional_arguments(self) -> None:
        self.assertEqual(_parse_ban_arguments("/ban 123"), (123, None, None))

    def test_temporary_ban_with_duration_before_reason(self) -> None:
        self.assertEqual(
            _parse_ban_arguments("/ban 123 3600 source API spam"),
            (123, 3600, "source API spam"),
        )

    def test_temporary_ban_accepts_duration_after_reason(self) -> None:
        self.assertEqual(
            _parse_ban_arguments("/ban 123 source API spam 3600"),
            (123, 3600, "source API spam"),
        )

    def test_permanent_ban_accepts_reason_without_duration(self) -> None:
        self.assertEqual(
            _parse_ban_arguments("/ban 123 repeated spam"),
            (123, None, "repeated spam"),
        )

    def test_invalid_or_missing_user_id_is_rejected(self) -> None:
        self.assertIsNone(_parse_ban_arguments("/ban"))
        self.assertIsNone(_parse_ban_arguments("/ban nope 60"))

    def test_non_positive_duration_is_rejected_in_both_positions(self) -> None:
        self.assertIsNone(_parse_ban_arguments("/ban 123 0"))
        self.assertIsNone(_parse_ban_arguments("/ban 123 -60 spam"))
        self.assertIsNone(_parse_ban_arguments("/ban 123 spam 0"))
        self.assertIsNone(_parse_ban_arguments("/ban 123 spam -60"))

    def test_mapping_history_limit_is_bounded(self) -> None:
        self.assertEqual(_parse_mapping_history_limit("/mapping_history"), 20)
        self.assertEqual(_parse_mapping_history_limit("/mapping_history 50"), 50)
        self.assertIsNone(_parse_mapping_history_limit("/mapping_history 0"))
        self.assertIsNone(_parse_mapping_history_limit("/mapping_history 101"))
        self.assertIsNone(_parse_mapping_history_limit("/mapping_history nope"))

    def test_mapping_mutation_parsers_require_reason_and_distinct_providers(
        self,
    ) -> None:
        self.assertEqual(
            _parse_mapping_set(
                "/mapping_set accept MAL 123 AniDB 456 verified manually"
            ),
            ("accept", "mal", "123", "anidb", "456", "verified manually"),
        )
        self.assertEqual(
            _parse_mapping_delete(
                "/mapping_delete MAL 123 AniDB 456 duplicate mapping"
            ),
            ("mal", "123", "anidb", "456", "duplicate mapping"),
        )
        self.assertIsNone(_parse_mapping_set("/mapping_set accept mal 1 mal 2 reason"))
        self.assertIsNone(_parse_mapping_set("/mapping_set accept mal 1 anidb 2"))
        self.assertIsNone(_parse_mapping_delete("/mapping_delete mal 1 anidb 2"))

    def test_mapping_override_and_history_lines_keep_audit_fields(self) -> None:
        override = MappingOverride(
            "mal",
            "123",
            "anidb",
            "456",
            "accept",
            "verified manually",
            "telegram:42",
            "2026-10-28T19:00:00+00:00",
        )
        history = MappingOverrideHistory(
            "mal",
            "123",
            "anidb",
            "456",
            "set",
            "accept",
            "verified manually",
            "telegram:42",
            "2026-10-28T19:00:00+00:00",
        )

        current = _mapping_override_line(override)
        audit = _mapping_history_line(history)
        for value in ("mal:123", "anidb:456", "verified manually", "telegram:42"):
            self.assertIn(value, current)
            self.assertIn(value, audit)
        self.assertIn("[accept]", current)
        self.assertIn("set accept", audit)

    def test_mapping_output_chunks_stay_below_telegram_limit(self) -> None:
        chunks = _chunk_lines(
            "Mapping overrides: 20",
            [f"route-{index} " + ("x" * 700) for index in range(20)],
            empty_text="empty",
        )
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(chunk) <= 3500 for chunk in chunks))

    def test_long_users_output_is_split_below_telegram_limit(self) -> None:
        chunks = _chunk_user_ids(list(range(1, 1500)), "ru")
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(chunk) <= 3500 for chunk in chunks))
        self.assertIn("1499", chunks[-1])


class _FakeTelegramSession:
    def __init__(self) -> None:
        self.methods: list[object] = []

    async def __call__(self, bot: Bot, method: object, timeout: int | None = None):
        del bot, timeout
        self.methods.append(method)
        return True

    async def close(self) -> None:
        return None


class AdminAiogramIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.session = _FakeTelegramSession()
        self.bot = Bot("123456:TESTTOKEN", session=self.session)
        self.dispatcher = Dispatcher()
        register_admin_handlers(self.dispatcher)
        self.update_id = 0

    async def asyncTearDown(self) -> None:
        await self.bot.session.close()

    async def _feed(self, text: str, *, user_id: int = 42) -> str:
        self.update_id += 1
        update = Update(
            update_id=self.update_id,
            message=Message(
                message_id=self.update_id,
                date=datetime.now(timezone.utc),
                chat=Chat(id=user_id, type="private"),
                from_user=User(
                    id=user_id,
                    is_bot=False,
                    first_name="Admin",
                ),
                text=text,
            ),
        )
        before = len(self.session.methods)
        await self.dispatcher.feed_update(self.bot, update)
        self.assertGreater(len(self.session.methods), before)
        return str(getattr(self.session.methods[-1], "text", ""))

    async def test_mapping_overrides_runs_through_command_filter_and_handler(
        self,
    ) -> None:
        override = MappingOverride(
            "mal",
            "123",
            "anidb",
            "456",
            "accept",
            "verified manually",
            "telegram:42",
            "2026-10-28T19:00:00+00:00",
        )
        with (
            patch("bots.telegram.admin.is_telegram_admin", return_value=True),
            patch("bots.telegram.admin.get_user_locale", return_value="ru"),
            patch(
                "bots.telegram.admin.list_mapping_overrides",
                return_value=[override],
            ),
        ):
            text = await self._feed("/mapping_overrides")

        self.assertIn("Mapping overrides: 1", text)
        self.assertIn("mal:123", text)
        self.assertIn("author=telegram:42", text)

    async def test_mapping_history_passes_requested_limit(self) -> None:
        with (
            patch("bots.telegram.admin.is_telegram_admin", return_value=True),
            patch("bots.telegram.admin.get_user_locale", return_value="ru"),
            patch(
                "bots.telegram.admin.list_mapping_override_history",
                return_value=[],
            ) as history,
        ):
            text = await self._feed("/mapping_history 7")

        history.assert_called_once_with(limit=7, newest_first=True)
        self.assertIn("История mapping overrides пока пуста", text)

    async def test_mapping_mutation_requires_second_explicit_confirmation(self) -> None:
        with (
            patch("bots.telegram.admin.is_telegram_admin", return_value=True),
            patch("bots.telegram.admin.get_user_locale", return_value="ru"),
            patch("bots.telegram.admin.set_mapping_override") as setter,
        ):
            preview = await self._feed(
                "/mapping_set accept mal 123 anidb 456 verified manually"
            )
            setter.assert_not_called()
            match = re.search(r"/mapping_confirm ([0-9a-f]{8})", preview)
            self.assertIsNotNone(match)
            token = match.group(1) if match is not None else ""

            confirmed = await self._feed(f"/mapping_confirm {token}")

        setter.assert_called_once_with(
            "mal",
            "123",
            "anidb",
            "456",
            action="accept",
            reason="verified manually",
            author="telegram:42",
        )
        self.assertIn("Mapping override применён", confirmed)

    async def test_mapping_database_error_is_reported_to_admin(self) -> None:
        with (
            patch("bots.telegram.admin.is_telegram_admin", return_value=True),
            patch("bots.telegram.admin.get_user_locale", return_value="ru"),
            patch(
                "bots.telegram.admin.set_mapping_override",
                side_effect=sqlite3.OperationalError("database is locked"),
            ),
        ):
            preview = await self._feed(
                "/mapping_set accept mal 123 anidb 456 verified manually"
            )
            match = re.search(r"/mapping_confirm ([0-9a-f]{8})", preview)
            self.assertIsNotNone(match)
            token = match.group(1) if match is not None else ""
            failed = await self._feed(f"/mapping_confirm {token}")

        self.assertIn("Не удалось применить изменение", failed)
        self.assertIn("database is locked", failed)

    async def test_mapping_confirmation_is_scoped_to_creating_admin(self) -> None:
        with (
            patch("bots.telegram.admin.is_telegram_admin", return_value=True),
            patch("bots.telegram.admin.get_user_locale", return_value="ru"),
            patch("bots.telegram.admin.set_mapping_override") as setter,
        ):
            preview = await self._feed(
                "/mapping_set reject mal 123 anidb 456 known mismatch",
                user_id=42,
            )
            match = re.search(r"/mapping_confirm ([0-9a-f]{8})", preview)
            self.assertIsNotNone(match)
            token = match.group(1) if match is not None else ""
            denied = await self._feed(f"/mapping_confirm {token}", user_id=43)

        setter.assert_not_called()
        self.assertIn("другому администратору", denied)

    async def test_non_admin_cannot_read_mapping_overrides(self) -> None:
        with (
            patch("bots.telegram.admin.is_telegram_admin", return_value=False),
            patch("bots.telegram.admin.get_user_locale", return_value="ru"),
            patch("bots.telegram.admin.list_mapping_overrides") as listing,
        ):
            text = await self._feed("/mapping_overrides", user_id=99)

        listing.assert_not_called()
        self.assertEqual(text, "Недостаточно прав.")


if __name__ == "__main__":
    unittest.main()
