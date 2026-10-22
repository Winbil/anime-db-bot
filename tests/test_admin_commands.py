from __future__ import annotations

import unittest

from bots.telegram.admin import _chunk_user_ids, _parse_ban_arguments


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

    def test_long_users_output_is_split_below_telegram_limit(self) -> None:
        chunks = _chunk_user_ids(list(range(1, 1500)), "ru")
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(chunk) <= 3500 for chunk in chunks))
        self.assertIn("1499", chunks[-1])


if __name__ == "__main__":
    unittest.main()
