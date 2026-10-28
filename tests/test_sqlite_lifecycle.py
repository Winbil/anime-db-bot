from __future__ import annotations

import sqlite3
import unittest

from core.sqlite import managed_sqlite_connection


class ManagedSQLiteConnectionTests(unittest.TestCase):
    def test_connection_is_closed_after_successful_transaction(self) -> None:
        connection = sqlite3.connect(":memory:")
        with managed_sqlite_connection(connection) as active:
            active.execute("CREATE TABLE example(value INTEGER)")
            active.execute("INSERT INTO example(value) VALUES (1)")

        with self.assertRaises(sqlite3.ProgrammingError):
            connection.execute("SELECT 1")

    def test_connection_is_rolled_back_and_closed_after_failure(self) -> None:
        connection = sqlite3.connect(":memory:")
        with self.assertRaisesRegex(RuntimeError, "boom"):
            with managed_sqlite_connection(connection) as active:
                active.execute("CREATE TABLE example(value INTEGER)")
                raise RuntimeError("boom")

        with self.assertRaises(sqlite3.ProgrammingError):
            connection.execute("SELECT 1")


if __name__ == "__main__":
    unittest.main()
