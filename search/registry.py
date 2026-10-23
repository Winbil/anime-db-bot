from __future__ import annotations

from core.contracts import AnimeSearchProvider
from search.providers.anilist import AniListSearchProvider
from search.providers.mal import MALSearchProvider
from search.providers.shikimori import ShikimoriSearchProvider

DEFAULT_SEARCH_PROVIDER_KEYS = ("shikimori", "mal", "anilist")


def get_search_provider_map() -> dict[str, AnimeSearchProvider]:
    """Return every text-search backend available for /anime selection."""
    return {
        "shikimori": ShikimoriSearchProvider(),
        "mal": MALSearchProvider(),
        "anilist": AniListSearchProvider(),
    }


def get_search_providers() -> tuple[AnimeSearchProvider, ...]:
    """Return providers used by fast ``/anime <title>`` search.

    Fast search intentionally uses every registered text-search provider. The
    result set is merged by source-independent identities, while later bounded
    alias expansion can use confirmed titles from those identities to bridge
    language differences between providers.
    """
    providers = get_search_provider_map()
    return tuple(providers[key] for key in DEFAULT_SEARCH_PROVIDER_KEYS)


def get_search_provider() -> tuple[AnimeSearchProvider, ...]:
    """Backward-compatible alias for older bot wiring."""
    return get_search_providers()