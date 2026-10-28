from __future__ import annotations

from core.capabilities import SourceCapability
from core.contracts import AnimeSearchProvider
from core.settings import SourceSettings
from core.source_keys import SourceKey
from sources.catalog import (
    get_search_provider_map,
    get_search_providers,
    source_keys_with,
)

DEFAULT_SEARCH_PROVIDER_KEYS: tuple[SourceKey, ...] = source_keys_with(
    SourceCapability.SEARCH
)


def get_search_provider(
    settings: SourceSettings | None = None,
) -> tuple[AnimeSearchProvider, ...]:
    """Backward-compatible alias for older bot wiring."""
    return get_search_providers(settings)


__all__ = [
    "DEFAULT_SEARCH_PROVIDER_KEYS",
    "get_search_provider",
    "get_search_provider_map",
    "get_search_providers",
]
