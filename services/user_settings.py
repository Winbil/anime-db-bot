from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, replace

from localization import DEFAULT_LOCALE, normalize_locale

MAX_USER_SETTINGS = 10000


@dataclass(frozen=True, slots=True)
class UserSettings:
    locale: str = DEFAULT_LOCALE


class InMemoryUserSettingsStore:
    """Small bounded repository for user preferences until persistent DB arrives.

    The API is intentionally repository-like so SQLite/Postgres can replace this
    implementation later without changing Telegram handlers or renderers.
    """

    def __init__(self, max_entries: int = MAX_USER_SETTINGS) -> None:
        self._max_entries = max(1, int(max_entries))
        self._items: OrderedDict[int, UserSettings] = OrderedDict()

    def get(self, user_id: int | None) -> UserSettings:
        if user_id is None:
            return UserSettings()
        settings = self._items.pop(int(user_id), None)
        if settings is None:
            return UserSettings()
        self._items[int(user_id)] = settings
        return settings

    def set_locale(self, user_id: int, locale: str) -> UserSettings:
        user_id = int(user_id)
        current = self.get(user_id)
        updated = replace(current, locale=normalize_locale(locale))
        self._items.pop(user_id, None)
        self._items[user_id] = updated
        while len(self._items) > self._max_entries:
            self._items.popitem(last=False)
        return updated

    def clear(self) -> None:
        self._items.clear()


USER_SETTINGS = InMemoryUserSettingsStore()


def get_user_locale(user_id: int | None) -> str:
    return USER_SETTINGS.get(user_id).locale


def set_user_locale(user_id: int, locale: str) -> str:
    return USER_SETTINGS.set_locale(user_id, locale).locale
