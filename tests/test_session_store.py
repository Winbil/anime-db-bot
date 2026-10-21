from __future__ import annotations

import unittest
from unittest.mock import patch

from bots.session_store import ExpiringSessionStore


class SessionStoreTests(unittest.TestCase):
    def test_session_expires_after_idle_ttl(self) -> None:
        store: ExpiringSessionStore[str] = ExpiringSessionStore(
            max_entries=5,
            ttl_seconds=10,
        )

        with patch("bots.session_store.time.monotonic", return_value=100.0):
            store["token"] = "value"
            self.assertEqual(store.get("token"), "value")

        with patch("bots.session_store.time.monotonic", return_value=111.0):
            self.assertIsNone(store.get("token"))
            self.assertEqual(len(store), 0)

    def test_live_read_extends_sliding_ttl(self) -> None:
        store: ExpiringSessionStore[str] = ExpiringSessionStore(
            max_entries=5,
            ttl_seconds=10,
        )

        with patch("bots.session_store.time.monotonic", return_value=100.0):
            store["token"] = "value"
        with patch("bots.session_store.time.monotonic", return_value=109.0):
            self.assertEqual(store.get("token"), "value")
        with patch("bots.session_store.time.monotonic", return_value=118.0):
            self.assertEqual(store.get("token"), "value")

    def test_oldest_session_is_evicted_at_capacity(self) -> None:
        store: ExpiringSessionStore[str] = ExpiringSessionStore(
            max_entries=2,
            ttl_seconds=100,
        )

        with patch("bots.session_store.time.monotonic", return_value=100.0):
            store["first"] = "1"
            store["second"] = "2"
            store["third"] = "3"
            self.assertIsNone(store.get("first"))
            self.assertEqual(store.get("second"), "2")
            self.assertEqual(store.get("third"), "3")

    def test_recently_used_session_survives_capacity_eviction(self) -> None:
        store: ExpiringSessionStore[str] = ExpiringSessionStore(
            max_entries=2,
            ttl_seconds=100,
        )

        with patch("bots.session_store.time.monotonic", return_value=100.0):
            store["first"] = "1"
            store["second"] = "2"
            self.assertEqual(store.get("first"), "1")
            store["third"] = "3"

            self.assertEqual(store.get("first"), "1")
            self.assertIsNone(store.get("second"))
            self.assertEqual(store.get("third"), "3")


if __name__ == "__main__":
    unittest.main()
