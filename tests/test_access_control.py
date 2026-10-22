from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from services.access_control import (
    UserRole,
    is_admin,
    is_telegram_admin,
    reset_access_control_cache,
    role_for,
    telegram_admin_ids,
)


class AccessControlTests(unittest.TestCase):
    def tearDown(self) -> None:
        reset_access_control_cache()

    def test_no_admins_configured_by_default(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            reset_access_control_cache()
            self.assertEqual(telegram_admin_ids(), frozenset())
            self.assertEqual(role_for("telegram", 123), UserRole.USER)
            self.assertFalse(is_telegram_admin(123))

    def test_configured_telegram_id_is_admin(self) -> None:
        with patch.dict(os.environ, {"ADMIN_TELEGRAM_USER_IDS": "123456789"}, clear=True):
            reset_access_control_cache()
            self.assertEqual(telegram_admin_ids(), frozenset({123456789}))
            self.assertEqual(role_for("telegram", 123456789), UserRole.ADMIN)
            self.assertTrue(is_admin("Telegram", 123456789))
            self.assertFalse(is_telegram_admin(987654321))

    def test_multiple_admin_ids_accept_common_separators_and_deduplicate(self) -> None:
        with patch.dict(
            os.environ,
            {"ADMIN_TELEGRAM_USER_IDS": "1, 2;3\n2"},
            clear=True,
        ):
            reset_access_control_cache()
            self.assertEqual(telegram_admin_ids(), frozenset({1, 2, 3}))

    def test_admin_role_is_platform_scoped(self) -> None:
        with patch.dict(os.environ, {"ADMIN_TELEGRAM_USER_IDS": "42"}, clear=True):
            reset_access_control_cache()
            self.assertEqual(role_for("telegram", 42), UserRole.ADMIN)
            self.assertEqual(role_for("discord", 42), UserRole.USER)
            self.assertEqual(role_for("telegram", None), UserRole.USER)

    def test_invalid_admin_configuration_fails_fast(self) -> None:
        with patch.dict(os.environ, {"ADMIN_TELEGRAM_USER_IDS": "123,not-an-id"}, clear=True):
            reset_access_control_cache()
            with self.assertRaises(ValueError):
                telegram_admin_ids()


if __name__ == "__main__":
    unittest.main()
