from __future__ import annotations

from services.aggregator import AnimeAggregator
from services.search import SearchService
from sources.registry import get_sources


SOURCES = get_sources()
SEARCH_SERVICE = SearchService(SOURCES)
AGGREGATOR = AnimeAggregator(SOURCES)


def source_names() -> tuple[str, ...]:
    return tuple(source.name for source in SOURCES)
