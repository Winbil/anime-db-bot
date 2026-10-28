from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager


@contextmanager
def managed_sqlite_connection(
    connection: sqlite3.Connection,
) -> Iterator[sqlite3.Connection]:
    """Commit/rollback like ``with connection`` and always close afterwards.

    ``sqlite3.Connection`` is a context manager for transactions only; leaving
    ``with connection:`` does not close the underlying database handle. Keeping
    that distinction in one helper prevents short-lived repository operations
    from accumulating open handles until garbage collection.
    """
    try:
        with connection:
            yield connection
    finally:
        connection.close()
