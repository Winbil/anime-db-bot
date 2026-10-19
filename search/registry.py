from __future__ import annotations

from core.contracts import AnimeSearchProvider
from search.mal import MALSearchProvider


def get_search_provider() -> AnimeSearchProvider:
    """Return the single search provider used by the bot."""
    return MALSearchProvider()
