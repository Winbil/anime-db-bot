from __future__ import annotations

from enum import StrEnum
from functools import lru_cache

from core.settings import get_settings, reload_settings


class UserRole(StrEnum):
    USER = "user"
    ADMIN = "admin"


@lru_cache(maxsize=1)
def telegram_admin_ids() -> frozenset[int]:
    """Return configured Telegram administrator account IDs."""
    return frozenset(get_settings().telegram.admin_user_ids)


def role_for(platform: str, user_id: int | None) -> UserRole:
    if user_id is None:
        return UserRole.USER

    platform_key = (platform or "").strip().casefold()
    if platform_key == "telegram" and int(user_id) in telegram_admin_ids():
        return UserRole.ADMIN
    return UserRole.USER


def is_admin(platform: str, user_id: int | None) -> bool:
    return role_for(platform, user_id) is UserRole.ADMIN


def is_telegram_admin(user_id: int | None) -> bool:
    return is_admin("telegram", user_id)


def reset_access_control_cache() -> None:
    """Clear cached configuration; intended for tests/config reload tooling."""
    telegram_admin_ids.cache_clear()
    reload_settings()
