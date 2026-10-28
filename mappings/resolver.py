from __future__ import annotations

import logging
import sqlite3
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from core.identity import AnimeIdentity
from mappings.config import mappings_db_path


@dataclass(frozen=True, slots=True)
class MappingOverride:
    source_provider: str
    source_id: str
    target_provider: str
    target_id: str
    action: str
    reason: str


def _clean_provider(value: object) -> str:
    return str(value or "").strip().casefold()


def _clean_id(value: object) -> str:
    return str(value or "").strip()


def _database_path(path: Path | None = None) -> Path:
    return Path(path) if path is not None else mappings_db_path()


def _validate_override(
    source_provider: object,
    source_id: object,
    target_provider: object,
    target_id: object,
    action: object,
    reason: object,
) -> MappingOverride:
    override = MappingOverride(
        source_provider=_clean_provider(source_provider),
        source_id=_clean_id(source_id),
        target_provider=_clean_provider(target_provider),
        target_id=_clean_id(target_id),
        action=str(action or "").strip().casefold(),
        reason=" ".join(str(reason or "").split()).strip(),
    )
    if not override.source_provider or not override.source_id:
        raise ValueError("source provider and source ID are required")
    if not override.target_provider or not override.target_id:
        raise ValueError("target provider and target ID are required")
    if override.source_provider == override.target_provider:
        raise ValueError("mapping overrides must connect different providers")
    if override.action not in {"accept", "reject"}:
        raise ValueError("override action must be accept or reject")
    if not override.reason:
        raise ValueError("override reason is required for auditability")
    return override


def list_mapping_overrides(path: Path | None = None) -> list[MappingOverride]:
    db_path = _database_path(path)
    if not db_path.is_file():
        return []
    uri = f"file:{db_path.resolve().as_posix()}?mode=ro"
    try:
        with sqlite3.connect(uri, uri=True, timeout=5.0) as conn:
            rows = conn.execute(
                """
                SELECT source_provider, source_id, target_provider, target_id,
                       action, reason
                FROM mapping_overrides
                ORDER BY source_provider, source_id, target_provider, target_id
                """
            ).fetchall()
    except sqlite3.OperationalError:
        return []
    return [MappingOverride(*map(str, row)) for row in rows]


def set_mapping_override(
    source_provider: object,
    source_id: object,
    target_provider: object,
    target_id: object,
    *,
    action: object,
    reason: object,
    path: Path | None = None,
) -> MappingOverride:
    override = _validate_override(
        source_provider,
        source_id,
        target_provider,
        target_id,
        action,
        reason,
    )
    db_path = _database_path(path)
    if not db_path.is_file():
        raise FileNotFoundError(f"mapping database does not exist: {db_path}")

    with sqlite3.connect(db_path, timeout=5.0) as conn:
        conn.execute(
            """
            INSERT INTO mapping_overrides(
                source_provider, source_id, target_provider, target_id,
                action, reason
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(source_provider, source_id, target_provider, target_id)
            DO UPDATE SET action=excluded.action, reason=excluded.reason
            """,
            (
                override.source_provider,
                override.source_id,
                override.target_provider,
                override.target_id,
                override.action,
                override.reason,
            ),
        )
        conn.commit()
    return override


def delete_mapping_override(
    source_provider: object,
    source_id: object,
    target_provider: object,
    target_id: object,
    *,
    path: Path | None = None,
) -> bool:
    values = (
        _clean_provider(source_provider),
        _clean_id(source_id),
        _clean_provider(target_provider),
        _clean_id(target_id),
    )
    if not all(values):
        raise ValueError("source/target provider and ID are required")
    db_path = _database_path(path)
    if not db_path.is_file():
        return False
    with sqlite3.connect(db_path, timeout=5.0) as conn:
        cursor = conn.execute(
            """
            DELETE FROM mapping_overrides
            WHERE source_provider=? AND source_id=?
              AND target_provider=? AND target_id=?
            """,
            values,
        )
        conn.commit()
        return cursor.rowcount > 0


def copy_mapping_overrides(
    source_path: Path,
    destination: sqlite3.Connection,
) -> int:
    source_path = Path(source_path)
    if not source_path.is_file():
        return 0
    uri = f"file:{source_path.resolve().as_posix()}?mode=ro"
    try:
        with sqlite3.connect(uri, uri=True, timeout=5.0) as source:
            rows = source.execute(
                """
                SELECT source_provider, source_id, target_provider, target_id,
                       action, reason
                FROM mapping_overrides
                """
            ).fetchall()
    except sqlite3.OperationalError:
        return 0

    destination.executemany(
        """
        INSERT OR REPLACE INTO mapping_overrides(
            source_provider, source_id, target_provider, target_id,
            action, reason
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
    destination.commit()
    return len(rows)


class MappingResolver:
    """Resolve only direct, unambiguous edges from already-confirmed IDs.

    Cross-catalog mappings are not generally transitive: one TVDB/TMDB entry can
    represent a season grouping that points back to several MAL/AniDB entries.
    Following arbitrary chains can therefore turn a correct anime identity into a
    related season or split entry. Runtime enrichment deliberately performs a
    single hop from source-confirmed IDs and requires every target provider to
    collapse to exactly one candidate.

    Directional manual overrides are applied after dataset evidence. ``accept``
    replaces automatic candidates for that exact source -> target-provider route;
    ``reject`` removes only the exact target ID. Confirmed source IDs remain more
    authoritative than both dataset evidence and overrides.
    """

    def __init__(self, path: Path | None = None) -> None:
        self.path = _database_path(path)

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

        edge_query = f"""
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
                END AS target_id
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
            ORDER BY s.provider, s.external_id, target_provider, target_id
        """
        override_query = f"""
            WITH seeds(provider, external_id) AS (
                {seed_sql}
            )
            SELECT
                s.provider,
                s.external_id,
                o.target_provider,
                o.target_id,
                o.action,
                o.reason
            FROM seeds AS s
            JOIN mapping_overrides AS o
              ON o.source_provider=s.provider
             AND o.source_id=s.external_id
            ORDER BY s.provider, s.external_id, o.target_provider, o.target_id
        """

        per_seed: dict[tuple[str, str], dict[str, set[str]]] = defaultdict(
            lambda: defaultdict(set)
        )
        accepts: dict[tuple[str, str, str], set[str]] = defaultdict(set)
        rejects: dict[tuple[str, str, str], set[str]] = defaultdict(set)
        try:
            with self._connect() as conn:
                for seed_provider, seed_id, target_provider, target_id in conn.execute(
                    edge_query,
                    params,
                ):
                    per_seed[(str(seed_provider), str(seed_id))][
                        str(target_provider)
                    ].add(str(target_id))
                try:
                    override_rows = conn.execute(override_query, params).fetchall()
                except sqlite3.OperationalError:
                    override_rows = []
        except (sqlite3.DatabaseError, OSError):
            logging.exception("Could not resolve direct external IDs from mappings.db")
            return {}

        for (
            seed_provider,
            seed_id,
            target_provider,
            target_id,
            action,
            _reason,
        ) in override_rows:
            key = (str(seed_provider), str(seed_id), str(target_provider))
            if str(action) == "accept":
                accepts[key].add(str(target_id))
            elif str(action) == "reject":
                rejects[key].add(str(target_id))

        for seed_provider, seed_id in seeds:
            seed_key = (seed_provider, seed_id)
            target_providers = set(per_seed.get(seed_key, {}))
            target_providers.update(
                target_provider
                for provider, external_id, target_provider in accepts
                if provider == seed_provider and external_id == seed_id
            )
            target_providers.update(
                target_provider
                for provider, external_id, target_provider in rejects
                if provider == seed_provider and external_id == seed_id
            )
            for target_provider in target_providers:
                route_key = (seed_provider, seed_id, target_provider)
                if accepts.get(route_key):
                    per_seed[seed_key][target_provider] = set(accepts[route_key])
                elif rejects.get(route_key):
                    per_seed[seed_key][target_provider].difference_update(
                        rejects[route_key]
                    )
                    if not per_seed[seed_key][target_provider]:
                        per_seed[seed_key].pop(target_provider, None)

        candidates: dict[str, dict[str, set[tuple[str, str]]]] = defaultdict(
            lambda: defaultdict(set)
        )
        for seed_key, targets in per_seed.items():
            for target_provider, target_ids in targets.items():
                for target_id in target_ids:
                    candidates[target_provider][target_id].add(seed_key)

        # A direct mapping that contradicts a source-confirmed ID makes this
        # enrichment attempt unsafe. Do not cherry-pick unrelated additions from
        # evidence that has already disagreed with the identity we trust more.
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
