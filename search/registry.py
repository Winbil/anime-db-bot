from __future__ import annotations

from core.contracts import AnimeSearchProvider
from search.providers.mal import MALSearchProvider
from search.providers.shikimori import ShikimoriSearchProvider


def get_search_providers() -> tuple[AnimeSearchProvider, ...]:
    """Return enabled search providers.

    Search providers only discover anime and MAL IDs. They are independent from
    metadata sources in sources/.
    """
    return (
        ShikimoriSearchProvider(),
        MALSearchProvider(),
    )
