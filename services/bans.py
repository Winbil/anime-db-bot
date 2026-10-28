from __future__ import annotations

import sqlite3
import threading
import time
from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Iterator

from core.settings import get_settings
from core.sqlite import managed_sqlite_connection


@dataclass(frozen=True, slots=True)
class BanRecord:
    platform: str
    user_id: int
    reason: str | None
    banned_by: int
    created_at: int
    expires_at: int | None

    @property
    def permanent(self) -> bool:
        return self.expires_at is None


class SQLiteBanStore:
    """Persistent moderation bans stored separately from user preferences."""

    def __init__(self, path: str | Path) -> None:
        self._path = str(path)
        self._initialized = False
        self._init_lock = threading.Lock()

    def _connect(self) -> sqlite3.Connection:
        if self._path != ":memory:":
            Path(self._path).expanduser().resolve().parent.mkdir(
                parents=True, exist_ok=True
            )
        connection = sqlite3.connect(self._path, timeout=5.0)
        connection.execute("PRAGMA busy_timeout = 5000")
        return connection

    def _ensure_schema(self) -> None:
        if self._initialized:
            return
        with self._init_lock:
            if self._initialized:
                return
            with managed_sqlite_connection(self._connect()) as connection:
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS bans (
                        platform TEXT NOT NULL,
                        user_id INTEGER NOT NULL,
                        reason TEXT,
                        banned_by INTEGER NOT NULL,
                        created_at INTEGER NOT NULL,
                        expires_at INTEGER,
                        PRIMARY KEY (platform, user_id)
                    )
                    """
                )
                connection.execute(
                    "CREATE INDEX IF NOT EXISTS idx_bans_expires_at ON bans(expires_at)"
                )
            self._initialized = True

    @staticmethod
    def _platform_key(platform: str) -> str:
        value = (platform or "").strip().casefold()
        if not value:
            raise ValueError("platform must not be empty")
        return value

    def ban(
        self,
        platform: str,
        user_id: int,
        *,
        banned_by: int,
        duration_seconds: int | None = None,
        reason: str | None = None,
        now: int | None = None,
    ) -> BanRecord:
        platform_key = self._platform_key(platform)
        user_id = int(user_id)
        banned_by = int(banned_by)
        if user_id <= 0 or banned_by <= 0:
            raise ValueError("user IDs must be positive")
        if duration_seconds is not None and int(duration_seconds) <= 0:
            raise ValueError("duration_seconds must be positive")

        created_at = int(time.time() if now is None else now)
        expires_at = (
            created_at + int(duration_seconds) if duration_seconds is not None else None
        )
        clean_reason = (reason or "").strip() or None

        self._ensure_schema()
        with managed_sqlite_connection(self._connect()) as connection:
            connection.execute(
                """
                INSERT INTO bans (
                    platform, user_id, reason, banned_by, created_at, expires_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(platform, user_id) DO UPDATE SET
                    reason = excluded.reason,
                    banned_by = excluded.banned_by,
                    created_at = excluded.created_at,
                    expires_at = excluded.expires_at
                """,
                (
                    platform_key,
                    user_id,
                    clean_reason,
                    banned_by,
                    created_at,
                    expires_at,
                ),
            )

        return BanRecord(
            platform_key, user_id, clean_reason, banned_by, created_at, expires_at
        )

    def get_active(
        self,
        platform: str,
        user_id: int,
        *,
        now: int | None = None,
    ) -> BanRecord | None:
        platform_key = self._platform_key(platform)
        current_time = int(time.time() if now is None else now)
        self._ensure_schema()

        with managed_sqlite_connection(self._connect()) as connection:
            row = connection.execute(
                """
                SELECT reason, banned_by, created_at, expires_at
                FROM bans
                WHERE platform = ? AND user_id = ?
                """,
                (platform_key, int(user_id)),
            ).fetchone()
            if row is None:
                return None

            expires_at = int(row[3]) if row[3] is not None else None
            if expires_at is not None and expires_at <= current_time:
                connection.execute(
                    "DELETE FROM bans WHERE platform = ? AND user_id = ?",
                    (platform_key, int(user_id)),
                )
                return None

        return BanRecord(
            platform=platform_key,
            user_id=int(user_id),
            reason=str(row[0]) if row[0] is not None else None,
            banned_by=int(row[1]),
            created_at=int(row[2]),
            expires_at=expires_at,
        )

    def unban(self, platform: str, user_id: int) -> bool:
        platform_key = self._platform_key(platform)
        self._ensure_schema()
        with managed_sqlite_connection(self._connect()) as connection:
            cursor = connection.execute(
                "DELETE FROM bans WHERE platform = ? AND user_id = ?",
                (platform_key, int(user_id)),
            )
        return cursor.rowcount > 0

    def clear(self) -> None:
        self._ensure_schema()
        with managed_sqlite_connection(self._connect()) as connection:
            connection.execute("DELETE FROM bans")


_CURRENT_BAN_STORE: ContextVar[SQLiteBanStore | None] = ContextVar(
    "anime_db_bot_ban_store",
    default=None,
)


@lru_cache(maxsize=1)
def _default_ban_store() -> SQLiteBanStore:
    """Compatibility store for standalone calls outside an active AppContext."""
    return SQLiteBanStore(get_settings().storage.bans_db_path)


def get_ban_store() -> SQLiteBanStore:
    return _CURRENT_BAN_STORE.get() or _default_ban_store()


@contextmanager
def activate_ban_store(store: SQLiteBanStore) -> Iterator[SQLiteBanStore]:
    token: Token[SQLiteBanStore | None] = _CURRENT_BAN_STORE.set(store)
    try:
        yield store
    finally:
        _CURRENT_BAN_STORE.reset(token)


def ban_user(
    platform: str,
    user_id: int,
    *,
    banned_by: int,
    duration_seconds: int | None = None,
    reason: str | None = None,
) -> BanRecord:
    return get_ban_store().ban(
        platform,
        user_id,
        banned_by=banned_by,
        duration_seconds=duration_seconds,
        reason=reason,
    )


def get_active_ban(platform: str, user_id: int) -> BanRecord | None:
    return get_ban_store().get_active(platform, user_id)


def unban_user(platform: str, user_id: int) -> bool:
    return get_ban_store().unban(platform, user_id)
