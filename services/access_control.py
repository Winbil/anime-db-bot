from __future__ import annotations

import os
import re
from enum import StrEnum
from functools import lru_cache


class UserRole(StrEnum):
    USER = "user"
    ADMIN = "admin"


_ADMIN_ID_SPLIT_RE = re.compile(r"[\s,;]+")


def _parse_positive_ids(raw: str, *, variable_name: str) -> frozenset[int]:
    values: set[int] = set()
    for token in _ADMIN_ID_SPLIT_RE.split((raw or "").strip()):
        if not token:
            continue
        if not token.isdecimal():
            raise ValueError(
                f"{variable_name} must contain positive numeric account IDs; got {token!r}"
            )
        value = int(token)
        if value <= 0:
            raise ValueError(
                f"{variable_name} must contain positive numeric account IDs; got {token!r}"
            )
        values.add(value)
    return frozenset(values)


@lru_cache(maxsize=1)
def telegram_admin_ids() -> frozenset[int]:
    """Return configured Telegram administrator account IDs.

    The value is intentionally configuration-owned rather than user-settings-owned:
    users must never be able to grant themselves privileged roles through the
    preferences database. The environment is read lazily so `.env` can be loaded
    by the application entrypoint before this configuration is first used.
    """

    return _parse_positive_ids(
        os.getenv("ADMIN_TELEGRAM_USER_IDS", ""),
        variable_name="ADMIN_TELEGRAM_USER_IDS",
    )


def role_for(platform: str, user_id: int | None) -> UserRole:
    """Resolve the current application role for a platform account."""

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
