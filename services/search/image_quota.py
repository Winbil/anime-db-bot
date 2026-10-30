from __future__ import annotations

import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from core.sqlite import managed_sqlite_connection


@dataclass(frozen=True, slots=True)
class DailyQuotaState:
    used: int
    exhausted: bool


class SQLiteImageSearchQuotaStore:
    """Persist conservative per-day usage for providers without a quota endpoint."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._init_schema()

    @staticmethod
    def period_key(now: datetime | None = None) -> str:
        value = now or datetime.now(timezone.utc)
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).date().isoformat()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        return connection

    def _init_schema(self) -> None:
        with self._lock, managed_sqlite_connection(self._connect()) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS image_search_quota (
                    provider TEXT NOT NULL,
                    period TEXT NOT NULL,
                    used INTEGER NOT NULL DEFAULT 0,
                    exhausted INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (provider, period)
                )
                """
            )

    def state(self, provider: str, *, period: str | None = None) -> DailyQuotaState:
        key = (provider or "").strip().casefold()
        day = period or self.period_key()
        with self._lock, managed_sqlite_connection(self._connect()) as connection:
            row = connection.execute(
                "SELECT used, exhausted FROM image_search_quota WHERE provider=? AND period=?",
                (key, day),
            ).fetchone()
        if row is None:
            return DailyQuotaState(0, False)
        return DailyQuotaState(max(0, int(row["used"])), bool(row["exhausted"]))

    def consume(
        self, provider: str, *, amount: int = 1, period: str | None = None
    ) -> None:
        key = (provider or "").strip().casefold()
        day = period or self.period_key()
        amount = max(0, int(amount))
        if not key or amount <= 0:
            return
        with self._lock, managed_sqlite_connection(self._connect()) as connection:
            connection.execute(
                """
                INSERT INTO image_search_quota(provider, period, used, exhausted)
                VALUES (?, ?, ?, 0)
                ON CONFLICT(provider, period) DO UPDATE SET used=used + excluded.used
                """,
                (key, day, amount),
            )

    def mark_exhausted(self, provider: str, *, period: str | None = None) -> None:
        key = (provider or "").strip().casefold()
        day = period or self.period_key()
        if not key:
            return
        with self._lock, managed_sqlite_connection(self._connect()) as connection:
            connection.execute(
                """
                INSERT INTO image_search_quota(provider, period, used, exhausted)
                VALUES (?, ?, 0, 1)
                ON CONFLICT(provider, period) DO UPDATE SET exhausted=1
                """,
                (key, day),
            )
