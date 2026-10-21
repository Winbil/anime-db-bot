from __future__ import annotations

import os
import sqlite3
import threading
from dataclasses import dataclass
from pathlib import Path

from localization import DEFAULT_LOCALE, normalize_locale

DEFAULT_DB_PATH = Path(__file__).resolve().parents[1] / "data" / "user_settings.sqlite3"


@dataclass(frozen=True, slots=True)
class UserSettings:
    locale: str = DEFAULT_LOCALE


class SQLiteUserSettingsStore:
    """Persistent repository for per-user interface preferences.

    Only the requested row is read, so the number of registered users does not
    translate into an equally large in-memory settings map. The repository API
    can later grow with the broader user database without changing bot handlers.
    """

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

    def clear(self) -> None:
        self._ensure_schema()
        with self._connect() as connection:
            connection.execute("DELETE FROM user_settings")


def _default_db_path() -> str:
    configured = os.getenv("USER_SETTINGS_DB_PATH", "").strip()
    return configured or str(DEFAULT_DB_PATH)


USER_SETTINGS = SQLiteUserSettingsStore(_default_db_path())


def get_user_locale(user_id: int | None) -> str:
    return USER_SETTINGS.get(user_id).locale


def set_user_locale(user_id: int, locale: str) -> str:
    return USER_SETTINGS.set_locale(user_id, locale).locale
