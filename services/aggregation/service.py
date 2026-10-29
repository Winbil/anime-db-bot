"""Compatibility surface for anime aggregation.

The active implementation is source-independent and lives in
``services.identity_aggregator``. Merge helpers are isolated in
``services.aggregation_merge``. This module intentionally contains no MAL-primary
aggregation path; existing imports can keep using ``services.aggregator`` while
callers migrate to the more explicit modules.
"""

from services.aggregation.merge import (
    AggregationMergeSupport,
    _best_text,
    _clean,
    _consensus_domain,
    _consensus_int,
    _consensus_text,
    _consensus_values,
    _dedupe_strings,
    _external_ids_conflict,
    _external_ids_match,
    _max_int,
    _merge_broadcasts,
    _merge_people,
    _merge_portraits,
    _merge_season,
    _merge_source_text,
    _merge_studios,
    _min_positive_int,
    _normalized_portraits,
    _person_names,
    _season_parts,
)
from services.identity.aggregator import AnimeAggregator

__all__ = ["AnimeAggregator", "AggregationMergeSupport"]
