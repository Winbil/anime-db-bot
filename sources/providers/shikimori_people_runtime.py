from __future__ import annotations

from typing import Any

from core.cache import BoundedTTLCache
from core.models import PersonCredit


class ShikimoriPeopleRuntime:
    """Per-source caches used by lazy Shikimori people loading."""

    def __init__(self) -> None:
        self.character_cache = BoundedTTLCache[str, dict[str, Any]](
            max_entries=2000, name="shikimori_character"
        )
        self.voice_cache = BoundedTTLCache[str, list[PersonCredit]](
            max_entries=1000, name="shikimori_voice"
        )
        self.role_index_cache = BoundedTTLCache[str, list[str]](
            max_entries=1000, name="shikimori_role_index"
        )
