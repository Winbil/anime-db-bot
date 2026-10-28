from __future__ import annotations

import logging
from collections.abc import Iterator
from typing import Any

from aiogram.types import Message

from bots.telegram.card.renderer import send_anime_view
from bots.telegram.card.state import remember_anime
from core.models import SearchCandidate
from localization import text
from services.app_context import get_app_context
from services.user_settings import get_user_locale


class _ContextAttributeProxy:
    """Compatibility view over one AppContext attribute.

    It never constructs services at import time. Legacy UI modules can migrate to
    explicit context access incrementally without restoring module-global service
    ownership.
    """

    def __init__(self, attribute: str) -> None:
        self._attribute = attribute

    def _value(self) -> Any:
        return getattr(get_app_context(), self._attribute)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._value(), name)

    def __iter__(self) -> Iterator[Any]:
        return iter(self._value())

    def __len__(self) -> int:
        return len(self._value())

    def __bool__(self) -> bool:
        return bool(self._value())

    # Keep common service methods visible on the proxy class itself so unittest
    # patching can replace them without activating an AppContext first.
    def display_name(self, *args: Any, **kwargs: Any) -> Any:
        return self._value().display_name(*args, **kwargs)


# Temporary compatibility surfaces for UI modules. These are lazy views, not
# service singletons; AppContext remains the sole owner of the actual objects.
SEARCH_PROVIDERS = _ContextAttributeProxy("search_providers")
SEARCH_SERVICE = _ContextAttributeProxy("search_service")
SOURCES = _ContextAttributeProxy("sources")
AGGREGATOR = _ContextAttributeProxy("aggregator")
CHARACTER_SERVICE = _ContextAttributeProxy("character_service")
EPISODE_SERVICE = _ContextAttributeProxy("episode_service")
TRAILER_SERVICE = _ContextAttributeProxy("trailer_service")


async def aggregate_and_send(
    message: Message,
    candidate: SearchCandidate,
    owner_user_id: int,
) -> None:
    locale = get_user_locale(owner_user_id)
    identity = candidate.identity
    if identity.is_empty():
        await message.answer(text("search", "result_unavailable", locale=locale))
        return

    try:
        anime = await get_app_context().aggregator.aggregate(candidate)
    except Exception as exc:
        logging.error(
            "Anime aggregation failed for %s: %s: %s",
            identity.describe(),
            type(exc).__name__,
            exc,
            exc_info=True,
        )
        await message.answer(text("search", "get_result_failed", locale=locale))
        return

    token = remember_anime(anime, owner_user_id)
    await send_anime_view(
        message,
        token,
        anime,
        section="main",
        page=0,
        locale=locale,
    )
