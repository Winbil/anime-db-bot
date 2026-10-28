from __future__ import annotations

import sqlite3
import threading
from dataclasses import dataclass
from pathlib import Path

from core.settings import get_settings
from localization import DEFAULT_LOCALE, normalize_locale


@dataclass(frozen=True, slots=True)
class UserSettings:
    locale: str = DEFAULT_LOCALE


class SQLiteUserSettingsStore:
    """Persistent repository for per-user preferences and known platform IDs."""

    def __init__(self, path: str | Path) -> None:
        self._path = str(path)
        self._initialized = False
        self._init_lock = threading.Lock()

    def _connect(self) -> sqlite3.Connection:
        if self._path != ":memory:":
            Path(self._path).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self._path, timeout=5.0)
        connection.execute("PRAGMA busy_timeout = 5000")
        return connection

    def _ensure_schema(self) -> None:
        if self._initialized:
            return
        with self._init_lock:
            if self._initialized:
                return
            with self._connect() as connection:
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS user_settings (
                        user_id INTEGER PRIMARY KEY,
                        locale TEXT NOT NULL DEFAULT 'ru',
                        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS known_users (
                        platform TEXT NOT NULL,
                        user_id INTEGER NOT NULL,
                        first_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        last_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        PRIMARY KEY (platform, user_id)
                    )
                    """
                )
                connection.execute(
                    """
                    INSERT OR IGNORE INTO known_users (
                        platform, user_id, first_seen_at, last_seen_at
                    )
                    SELECT 'telegram', user_id, updated_at, updated_at
                    FROM user_settings
                    """
                )
            self._initialized = True

    def get(self, user_id: int | None) -> UserSettings:
        if user_id is None:
            return UserSettings()
        self._ensure_schema()
        with self._connect() as connection:
            row = connection.execute(
                "SELECT locale FROM user_settings WHERE user_id = ?",
                (int(user_id),),
            ).fetchone()
        if row is None:
            return UserSettings()
        return UserSettings(locale=normalize_locale(str(row[0])))

    def set_locale(self, user_id: int, locale: str) -> UserSettings:
        self._ensure_schema()
        normalized = normalize_locale(locale)
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO user_settings (user_id, locale, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(user_id) DO UPDATE SET
                    locale = excluded.locale,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (int(user_id), normalized),
            )
        return UserSettings(locale=normalized)

    def touch_user(self, platform: str, user_id: int) -> None:
        platform_key = (platform or "").strip().casefold()
        if not platform_key:
            raise ValueError("platform must not be empty")
        user_id = int(user_id)
        if user_id <= 0:
            raise ValueError("user_id must be positive")

        self._ensure_schema()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO known_users (platform, user_id, first_seen_at, last_seen_at)
                VALUES (?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                ON CONFLICT(platform, user_id) DO UPDATE SET
                    last_seen_at = CURRENT_TIMESTAMP
                """,
                (platform_key, user_id),
            )

    def list_user_ids(self, platform: str) -> list[int]:
        platform_key = (platform or "").strip().casefold()
        if not platform_key:
            return []
        self._ensure_schema()
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT user_id FROM known_users WHERE platform = ? ORDER BY user_id",
                (platform_key,),
            ).fetchall()
        return [int(row[0]) for row in rows]

    def clear(self) -> None:
        self._ensure_schema()
        with self._connect() as connection:
            connection.execute("DELETE FROM user_settings")
            connection.execute("DELETE FROM known_users")


USER_SETTINGS = SQLiteUserSettingsStore(get_settings().storage.user_settings_db_path)


def get_user_locale(user_id: int | None) -> str:
    return USER_SETTINGS.get(user_id).locale


def set_user_locale(user_id: int, locale: str) -> str:
    return USER_SETTINGS.set_locale(user_id, locale).locale


def touch_platform_user(platform: str, user_id: int) -> None:
    USER_SETTINGS.touch_user(platform, user_id)


def list_platform_user_ids(platform: str) -> list[int]:
    return USER_SETTINGS.list_user_ids(platform)
