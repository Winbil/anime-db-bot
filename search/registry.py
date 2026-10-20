from __future__ import annotations

from core.contracts import AnimeSearchProvider
from search.providers.anilist import AniListSearchProvider
from search.providers.mal import MALSearchProvider
from search.providers.shikimori import ShikimoriSearchProvider

DEFAULT_SEARCH_PROVIDER_KEYS = ("shikimori", "mal")


def get_search_provider_map() -> dict[str, AnimeSearchProvider]:
    """Return every search backend available for explicit selection."""
    return {
        "shikimori": ShikimoriSearchProvider(),
        "mal": MALSearchProvider(),
        "anilist": AniListSearchProvider(),
    }


def get_search_providers() -> tuple[AnimeSearchProvider, ...]:
    """Return providers used by the default /anime search.

    AniList is intentionally excluded from the default search to avoid spending
    its stricter rate limit on every user query. It remains available through
    the explicit /search command.
    """
    providers = get_search_provider_map()
    return tuple(providers[key] for key in DEFAULT_SEARCH_PROVIDER_KEYS)


def get_search_provider() -> tuple[AnimeSearchProvider, ...]:
    """Backward-compatible alias for older bot wiring."""
    return get_search_providers()
