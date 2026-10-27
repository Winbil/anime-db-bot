from __future__ import annotations

import logging
import sqlite3
from collections import defaultdict
from pathlib import Path

from core.identity import AnimeIdentity
from mappings.config import mappings_db_path


class MappingResolver:
    """Resolve only direct, unambiguous edges from already-confirmed IDs.

    Cross-catalog mappings are not generally transitive: one TVDB/TMDB entry can
    represent a season grouping that points back to several MAL/AniDB entries.
    Following arbitrary chains can therefore turn a correct anime identity into a
    related season or split entry. Runtime enrichment deliberately performs a
    single hop from source-confirmed IDs and requires every target provider to
    collapse to exactly one candidate.
    """

    def __init__(self, path: Path | None = None) -> None:
        self.path = Path(path) if path is not None else mappings_db_path()

    @property
    def available(self) -> bool:
        return self.path.is_file()

    def _connect(self) -> sqlite3.Connection:
        uri = f"file:{self.path.resolve().as_posix()}?mode=ro"
        conn = sqlite3.connect(uri, uri=True, timeout=5.0)
        conn.execute("PRAGMA query_only=ON")
        conn.execute("PRAGMA temp_store=FILE")
        return conn

    def resolve(self, identity: AnimeIdentity) -> dict[str, str]:
        if not self.available or identity.is_empty():
            return {}

        seeds = sorted(identity.external_ids.items())
        seed_sql = " UNION ALL ".join(
            "SELECT ? AS provider, ? AS external_id" for _ in seeds
        )
        params: list[str] = []
        for provider, external_id in seeds:
            params.extend([provider, external_id])

        query = f"""
            WITH seeds(provider, external_id) AS (
                {seed_sql}
            )
            SELECT
                s.provider,
                s.external_id,
                CASE
                    WHEN e.a_provider=s.provider AND e.a_id=s.external_id
                    THEN e.b_provider ELSE e.a_provider
                END AS target_provider,
                CASE
                    WHEN e.a_provider=s.provider AND e.a_id=s.external_id
                    THEN e.b_id ELSE e.a_id
                END AS target_id,
                e.confidence,
                e.evidence_count,
                e.evidence_group_count,
                e.max_weight
            FROM seeds AS s
            JOIN edges AS e
              ON e.status='accepted'
             AND (
                (e.a_provider=s.provider AND e.a_id=s.external_id)
                OR
                (e.b_provider=s.provider AND e.b_id=s.external_id)
             )
            WHERE NOT EXISTS (
                SELECT 1 FROM conflicts AS c
                WHERE c.source_provider=s.provider
                  AND c.source_id=s.external_id
                  AND c.target_provider=(
                    CASE
                        WHEN e.a_provider=s.provider AND e.a_id=s.external_id
                        THEN e.b_provider ELSE e.a_provider
                    END
                  )
            )
            ORDER BY target_provider, target_id, s.provider, s.external_id
        """

        candidates: dict[str, dict[str, set[tuple[str, str]]]] = defaultdict(
            lambda: defaultdict(set)
        )
        try:
            with self._connect() as conn:
                for (
                    seed_provider,
                    seed_id,
                    target_provider,
                    target_id,
                    _confidence,
                    _evidence_count,
                    _evidence_group_count,
                    _max_weight,
                ) in conn.execute(query, params):
                    candidates[str(target_provider)][str(target_id)].add(
                        (str(seed_provider), str(seed_id))
                    )
        except (sqlite3.DatabaseError, OSError):
            logging.exception("Could not resolve direct external IDs from mappings.db")
            return {}

        # A direct mapping that contradicts a source-confirmed ID makes this
        # enrichment attempt unsafe. Do not cherry-pick unrelated additions from
        # a graph that has already disagreed with the identity we trust more.
        for provider, known_id in identity.external_ids.items():
            provider_candidates = candidates.get(provider)
            if not provider_candidates:
                continue
            if set(provider_candidates) != {known_id}:
                logging.warning(
                    "Direct mapping evidence conflicts with confirmed %s:%s -> %s",
                    provider,
                    known_id,
                    sorted(provider_candidates),
                )
                return {}

        additions: dict[str, str] = {}
        for provider, provider_candidates in candidates.items():
            if provider in identity.external_ids:
                continue
            if len(provider_candidates) == 1:
                additions[provider] = next(iter(provider_candidates))
                continue
            if provider_candidates:
                logging.info(
                    "Skipping ambiguous direct %s mappings for %s: %s",
                    provider,
                    identity.describe(),
                    sorted(provider_candidates),
                )
        return additions

    def enrich(self, identity: AnimeIdentity) -> AnimeIdentity:
        enriched = identity.copy()
        enriched.merge_missing(self.resolve(enriched))
        return enriched


MAPPING_RESOLVER = MappingResolver()
