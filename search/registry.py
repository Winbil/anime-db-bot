from __future__ import annotations

from core.capabilities import SourceCapability, source_keys_with
from core.contracts import AnimeSearchProvider
from core.source_keys import SourceKey
from search.providers.anilist import AniListSearchProvider
from search.providers.mal import MALSearchProvider
from search.providers.shikimori import ShikimoriSearchProvider

DEFAULT_SEARCH_PROVIDER_KEYS: tuple[SourceKey, ...] = source_keys_with(
    SourceCapability.SEARCH
)

_SEARCH_FACTORIES = {
    SourceKey.SHIKIMORI: ShikimoriSearchProvider,
    SourceKey.MAL: MALSearchProvider,
    SourceKey.ANILIST: AniListSearchProvider,
}


def get_search_provider_map() -> dict[SourceKey, AnimeSearchProvider]:
    """Return every text-search backend declared by the capability catalog."""
    return {
        key: _SEARCH_FACTORIES[key]()
        for key in DEFAULT_SEARCH_PROVIDER_KEYS
        if key in _SEARCH_FACTORIES
    }


def get_search_providers() -> tuple[AnimeSearchProvider, ...]:
    """Return providers used by fast ``/anime <title>`` search.

    Fast search intentionally uses every registered text-search provider. The
    result set is merged by source-independent identities, while later bounded
    alias expansion can use confirmed titles from those identities to bridge
    language differences between providers.
    """
    providers = get_search_provider_map()
    return tuple(providers[key] for key in DEFAULT_SEARCH_PROVIDER_KEYS if key in providers)


def get_search_provider() -> tuple[AnimeSearchProvider, ...]:
    """Backward-compatible alias for older bot wiring."""
    return get_search_providers()
