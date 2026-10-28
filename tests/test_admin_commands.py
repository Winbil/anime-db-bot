from __future__ import annotations

import unittest

from bots.telegram.admin import (
    _chunk_lines,
    _chunk_user_ids,
    _mapping_history_line,
    _mapping_override_line,
    _parse_ban_arguments,
    _parse_mapping_history_limit,
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


if __name__ == "__main__":
    unittest.main()
