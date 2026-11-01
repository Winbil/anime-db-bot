from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from core.sqlite import managed_sqlite_connection
from mappings.config import MappingSourceSpec, mappings_db_path

SCHEMA_VERSION = 3


@dataclass(frozen=True, slots=True)
class MappingRecord:
    record_key: str
    ids: dict[str, tuple[str, ...]]
    evidence_group: str
    weight: int


@dataclass(frozen=True, slots=True)
class MappingBuildStats:
    datasets: int
    records: int
    evidence: int
    edges: int
    accepted_edges: int
    conflicts: int


def _clean_provider(value: object) -> str:
    return str(value or "").strip().casefold()


def _clean_id(value: object) -> str:
    return str(value or "").strip()


class MappingDatabaseBuilder:
    """Build compact runtime and provenance databases from streamed mappings.

    ``path`` is the small runtime database consumed by :class:`MappingResolver`.
    Provenance is written to ``evidence_path`` instead of being duplicated inside
    the runtime database. Both databases normalize ``(provider, external_id)`` to
    integer node IDs, so repeated provider/ID strings are stored only once.

    Importers still stream one source record at a time. The only in-memory global
    structure is a compact node/group ID cache; source datasets are never loaded
    wholesale into Python memory.
    """

    def __init__(self, path: Path, *, evidence_path: Path | None = None) -> None:
        self.path = Path(path)
        self.evidence_path = (
            Path(evidence_path)
            if evidence_path is not None
            else self.path.with_name(f"{self.path.stem}-evidence{self.path.suffix}")
        )
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.evidence_path.parent.mkdir(parents=True, exist_ok=True)
        self.path.unlink(missing_ok=True)
        self.evidence_path.unlink(missing_ok=True)

        self.conn = sqlite3.connect(self.path)
        self.conn.execute("PRAGMA journal_mode=OFF")
        self.conn.execute("PRAGMA synchronous=OFF")
        self.conn.execute("PRAGMA temp_store=FILE")
        self.conn.execute("PRAGMA foreign_keys=ON")

        self.evidence_conn = sqlite3.connect(self.evidence_path)
        self.evidence_conn.execute("PRAGMA journal_mode=OFF")
        self.evidence_conn.execute("PRAGMA synchronous=OFF")
        self.evidence_conn.execute("PRAGMA temp_store=FILE")
        self.evidence_conn.execute("PRAGMA foreign_keys=ON")

        self._node_cache: dict[tuple[str, str], int] = {}
        self._group_cache: dict[str, int] = {}
        self._create_runtime_schema()
        self._create_evidence_schema()

    def _create_runtime_schema(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE metadata (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            CREATE TABLE nodes (
                id INTEGER PRIMARY KEY,
                provider TEXT NOT NULL,
                external_id TEXT NOT NULL,
                UNIQUE(provider, external_id)
            );

            CREATE TABLE edges (
                a_node INTEGER NOT NULL REFERENCES nodes(id),
                b_node INTEGER NOT NULL REFERENCES nodes(id),
                confidence INTEGER NOT NULL,
                status TEXT NOT NULL,
                evidence_count INTEGER NOT NULL,
                evidence_group_count INTEGER NOT NULL,
                max_weight INTEGER NOT NULL,
                PRIMARY KEY (a_node, b_node)
            ) WITHOUT ROWID;

            CREATE INDEX edges_a_lookup_idx
                ON edges(a_node, status, b_node);
            CREATE INDEX edges_b_lookup_idx
                ON edges(b_node, status, a_node);

            CREATE TABLE conflicts (
                source_node INTEGER NOT NULL REFERENCES nodes(id),
                target_provider TEXT NOT NULL,
                candidate_ids_json TEXT NOT NULL,
                reason TEXT NOT NULL,
                PRIMARY KEY (source_node, target_provider)
            ) WITHOUT ROWID;

            CREATE TABLE mapping_overrides (
                source_provider TEXT NOT NULL,
                source_id TEXT NOT NULL,
                target_provider TEXT NOT NULL,
                target_id TEXT NOT NULL,
                action TEXT NOT NULL CHECK(action IN ('accept', 'reject')),
                reason TEXT NOT NULL DEFAULT '',
                author TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL DEFAULT '',
                PRIMARY KEY (
                    source_provider, source_id, target_provider, target_id
                )
            ) WITHOUT ROWID;

            CREATE TABLE mapping_override_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_provider TEXT NOT NULL,
                source_id TEXT NOT NULL,
                target_provider TEXT NOT NULL,
                target_id TEXT NOT NULL,
                event TEXT NOT NULL CHECK(event IN ('set', 'delete')),
                override_action TEXT NOT NULL CHECK(override_action IN ('accept', 'reject')),
                reason TEXT NOT NULL DEFAULT '',
                author TEXT NOT NULL DEFAULT '',
                changed_at TEXT NOT NULL
            );

            CREATE INDEX mapping_override_history_route_idx
                ON mapping_override_history(
                    source_provider, source_id, target_provider, target_id, changed_at
                );
            """
        )
        self.conn.executemany(
            "INSERT INTO metadata(key, value) VALUES(?, ?)",
            (("schema_version", str(SCHEMA_VERSION)), ("database_role", "runtime")),
        )
        self.conn.commit()

    def _create_evidence_schema(self) -> None:
        self.evidence_conn.executescript(
            """
            CREATE TABLE metadata (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            CREATE TABLE datasets (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL UNIQUE,
                source_url TEXT NOT NULL,
                importer TEXT NOT NULL,
                license_note TEXT NOT NULL,
                sha256 TEXT NOT NULL,
                downloaded_at TEXT NOT NULL,
                record_count INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE nodes (
                id INTEGER PRIMARY KEY,
                provider TEXT NOT NULL,
                external_id TEXT NOT NULL,
                UNIQUE(provider, external_id)
            );

            CREATE TABLE evidence_groups (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL UNIQUE
            );

            CREATE TABLE records (
                id INTEGER PRIMARY KEY,
                dataset_id INTEGER NOT NULL REFERENCES datasets(id) ON DELETE CASCADE,
                record_key TEXT NOT NULL,
                evidence_group_id INTEGER NOT NULL REFERENCES evidence_groups(id),
                weight INTEGER NOT NULL,
                UNIQUE(dataset_id, record_key, evidence_group_id)
            );

            CREATE INDEX records_dataset_idx ON records(dataset_id, id);

            CREATE TABLE edge_evidence (
                record_id INTEGER NOT NULL REFERENCES records(id) ON DELETE CASCADE,
                a_node INTEGER NOT NULL REFERENCES nodes(id),
                b_node INTEGER NOT NULL REFERENCES nodes(id),
                PRIMARY KEY (record_id, a_node, b_node)
            ) WITHOUT ROWID;
            """
        )
        self.evidence_conn.executemany(
            "INSERT INTO metadata(key, value) VALUES(?, ?)",
            (("schema_version", str(SCHEMA_VERSION)), ("database_role", "evidence")),
        )
        self.evidence_conn.commit()

    def _node_id(self, provider: str, external_id: str) -> int:
        key = (provider, external_id)
        cached = self._node_cache.get(key)
        if cached is not None:
            return cached
        self.evidence_conn.execute(
            "INSERT OR IGNORE INTO nodes(provider, external_id) VALUES (?, ?)",
            key,
        )
        row = self.evidence_conn.execute(
            "SELECT id FROM nodes WHERE provider=? AND external_id=?",
            key,
        ).fetchone()
        if row is None:
            raise RuntimeError(
                f"Could not allocate mapping node {provider}:{external_id}"
            )
        node_id = int(row[0])
        self._node_cache[key] = node_id
        return node_id

    def _group_id(self, name: str) -> int:
        cleaned = str(name or "").strip() or "unknown"
        cached = self._group_cache.get(cleaned)
        if cached is not None:
            return cached
        self.evidence_conn.execute(
            "INSERT OR IGNORE INTO evidence_groups(name) VALUES (?)",
            (cleaned,),
        )
        row = self.evidence_conn.execute(
            "SELECT id FROM evidence_groups WHERE name=?",
            (cleaned,),
        ).fetchone()
        if row is None:
            raise RuntimeError(f"Could not allocate evidence group {cleaned}")
        group_id = int(row[0])
        self._group_cache[cleaned] = group_id
        return group_id

    def ingest_dataset(
        self,
        spec: MappingSourceSpec,
        records: Iterable[MappingRecord],
        *,
        sha256: str,
        downloaded_at: str,
    ) -> int:
        cursor = self.evidence_conn.execute(
            """
            INSERT INTO datasets(
                name, source_url, importer, license_note, sha256, downloaded_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                spec.name,
                spec.url,
                spec.importer,
                spec.license_note,
                sha256,
                downloaded_at,
            ),
        )
        if cursor.lastrowid is None:
            raise RuntimeError("SQLite did not return a dataset row ID")
        dataset_id = int(cursor.lastrowid)
        record_count = 0

        for record in records:
            if self._insert_record(dataset_id, record):
                record_count += 1
            if record_count and record_count % 5000 == 0:
                self.evidence_conn.commit()

        self.evidence_conn.execute(
            "UPDATE datasets SET record_count=? WHERE id=?",
            (record_count, dataset_id),
        )
        self.evidence_conn.commit()
        return record_count

    def _insert_record(self, dataset_id: int, record: MappingRecord) -> bool:
        clean_nodes: list[tuple[str, str, int]] = []
        seen: set[tuple[str, str]] = set()
        for raw_provider, raw_values in record.ids.items():
            provider = _clean_provider(raw_provider)
            if not provider:
                continue
            for raw_id in raw_values:
                external_id = _clean_id(raw_id)
                key = (provider, external_id)
                if external_id and key not in seen:
                    seen.add(key)
                    clean_nodes.append((provider, external_id, self._node_id(*key)))

        if len({provider for provider, _external_id, _node_id in clean_nodes}) < 2:
            return False

        group_id = self._group_id(record.evidence_group)
        weight = max(0, min(int(record.weight), 100))
        self.evidence_conn.execute(
            """
            INSERT OR IGNORE INTO records(
                dataset_id, record_key, evidence_group_id, weight
            ) VALUES (?, ?, ?, ?)
            """,
            (dataset_id, str(record.record_key), group_id, weight),
        )
        row = self.evidence_conn.execute(
            """
            SELECT id FROM records
            WHERE dataset_id=? AND record_key=? AND evidence_group_id=?
            """,
            (dataset_id, str(record.record_key), group_id),
        ).fetchone()
        if row is None:
            raise RuntimeError("Could not allocate mapping evidence record")
        record_id = int(row[0])

        inserted = False
        for left_index, (left_provider, _left_external_id, left_node) in enumerate(
            clean_nodes
        ):
            for right_provider, _right_external_id, right_node in clean_nodes[
                left_index + 1 :
            ]:
                if left_provider == right_provider:
                    continue
                a_node, b_node = sorted((left_node, right_node))
                self.evidence_conn.execute(
                    """
                    INSERT OR IGNORE INTO edge_evidence(record_id, a_node, b_node)
                    VALUES (?, ?, ?)
                    """,
                    (record_id, a_node, b_node),
                )
                inserted = True
        return inserted

    def copy_dataset_from(
        self,
        source_path: Path,
        dataset_name: str,
        *,
        checked_at: str | None = None,
    ) -> int:
        """Copy a normalized v3 evidence dataset into a new atomic rebuild."""

        source_path = Path(source_path)
        if not source_path.is_file():
            return 0
        source_uri = source_path.resolve().as_posix()
        try:
            self.evidence_conn.execute("ATTACH DATABASE ? AS source_db", (source_uri,))
            schema_row = self.evidence_conn.execute(
                """
                SELECT 1 FROM source_db.sqlite_master
                WHERE type='table' AND name='records'
                """
            ).fetchone()
            if schema_row is None:
                return 0
            row = self.evidence_conn.execute(
                """
                SELECT id, source_url, importer, license_note, sha256,
                       downloaded_at, record_count
                FROM source_db.datasets WHERE name=?
                """,
                (dataset_name,),
            ).fetchone()
            if row is None:
                return 0
            (
                source_dataset_id,
                source_url,
                importer,
                license_note,
                sha256,
                downloaded_at,
                record_count,
            ) = row
            cursor = self.evidence_conn.execute(
                """
                INSERT INTO datasets(
                    name, source_url, importer, license_note, sha256,
                    downloaded_at, record_count
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    dataset_name,
                    source_url,
                    importer,
                    license_note,
                    sha256,
                    checked_at or downloaded_at,
                    int(record_count or 0),
                ),
            )
            if cursor.lastrowid is None:
                raise RuntimeError("SQLite did not return a copied dataset row ID")
            destination_dataset_id = int(cursor.lastrowid)

            self.evidence_conn.execute(
                """
                INSERT OR IGNORE INTO evidence_groups(name)
                SELECT DISTINCT g.name
                FROM source_db.records AS r
                JOIN source_db.evidence_groups AS g ON g.id=r.evidence_group_id
                WHERE r.dataset_id=?
                """,
                (source_dataset_id,),
            )
            self.evidence_conn.execute(
                """
                INSERT OR IGNORE INTO nodes(provider, external_id)
                SELECT DISTINCT n.provider, n.external_id
                FROM source_db.nodes AS n
                JOIN (
                    SELECT ee.a_node AS node_id
                    FROM source_db.edge_evidence AS ee
                    JOIN source_db.records AS r ON r.id=ee.record_id
                    WHERE r.dataset_id=?
                    UNION
                    SELECT ee.b_node AS node_id
                    FROM source_db.edge_evidence AS ee
                    JOIN source_db.records AS r ON r.id=ee.record_id
                    WHERE r.dataset_id=?
                ) AS used ON used.node_id=n.id
                """,
                (source_dataset_id, source_dataset_id),
            )
            self.evidence_conn.execute(
                """
                INSERT INTO records(dataset_id, record_key, evidence_group_id, weight)
                SELECT ?, sr.record_key, dg.id, sr.weight
                FROM source_db.records AS sr
                JOIN source_db.evidence_groups AS sg ON sg.id=sr.evidence_group_id
                JOIN evidence_groups AS dg ON dg.name=sg.name
                WHERE sr.dataset_id=?
                """,
                (destination_dataset_id, source_dataset_id),
            )
            self.evidence_conn.execute(
                """
                INSERT OR IGNORE INTO edge_evidence(record_id, a_node, b_node)
                SELECT
                    dr.id,
                    CASE WHEN da.id < db.id THEN da.id ELSE db.id END,
                    CASE WHEN da.id < db.id THEN db.id ELSE da.id END
                FROM source_db.edge_evidence AS se
                JOIN source_db.records AS sr ON sr.id=se.record_id
                JOIN source_db.evidence_groups AS sg ON sg.id=sr.evidence_group_id
                JOIN evidence_groups AS dg ON dg.name=sg.name
                JOIN records AS dr
                  ON dr.dataset_id=?
                 AND dr.record_key=sr.record_key
                 AND dr.evidence_group_id=dg.id
                JOIN source_db.nodes AS sa ON sa.id=se.a_node
                JOIN source_db.nodes AS sb ON sb.id=se.b_node
                JOIN nodes AS da
                  ON da.provider=sa.provider AND da.external_id=sa.external_id
                JOIN nodes AS db
                  ON db.provider=sb.provider AND db.external_id=sb.external_id
                WHERE sr.dataset_id=?
                """,
                (destination_dataset_id, source_dataset_id),
            )
            self.evidence_conn.commit()
            self._node_cache.clear()
            self._group_cache.clear()
            return int(record_count or 0)
        except sqlite3.OperationalError:
            self.evidence_conn.rollback()
            return 0
        finally:
            try:
                self.evidence_conn.execute("DETACH DATABASE source_db")
            except sqlite3.OperationalError:
                pass

    def finalize(self, *, built_at: str) -> MappingBuildStats:
        self.evidence_conn.commit()
        self.conn.execute("DELETE FROM conflicts")
        self.conn.execute("DELETE FROM edges")
        self.conn.execute("DELETE FROM nodes")
        self.conn.commit()

        evidence_uri = self.evidence_path.resolve().as_posix()
        self.conn.execute("ATTACH DATABASE ? AS ev", (evidence_uri,))
        try:
            self.conn.execute(
                "INSERT INTO nodes(id, provider, external_id) SELECT id, provider, external_id FROM ev.nodes"
            )
            self.conn.execute(
                """
                INSERT INTO edges(
                    a_node, b_node, confidence, status, evidence_count,
                    evidence_group_count, max_weight
                )
                SELECT
                    ee.a_node,
                    ee.b_node,
                    MIN(
                        100,
                        MAX(r.weight)
                        + 8 * (COUNT(DISTINCT r.evidence_group_id) - 1)
                        + 2 * MIN(
                            5,
                            COUNT(*) - COUNT(DISTINCT r.evidence_group_id)
                        )
                    ) AS confidence,
                    CASE
                        WHEN MAX(r.weight) >= 80
                             OR COUNT(DISTINCT r.evidence_group_id) >= 2
                        THEN 'accepted'
                        ELSE 'candidate'
                    END AS status,
                    COUNT(*) AS evidence_count,
                    COUNT(DISTINCT r.evidence_group_id) AS evidence_group_count,
                    MAX(r.weight) AS max_weight
                FROM ev.edge_evidence AS ee
                JOIN ev.records AS r ON r.id=ee.record_id
                GROUP BY ee.a_node, ee.b_node
                """
            )
            self.conn.commit()
        finally:
            self.conn.execute("DETACH DATABASE ev")

        self._build_directional_conflicts()

        stats = MappingBuildStats(
            datasets=self._evidence_scalar("SELECT COUNT(*) FROM datasets"),
            records=self._evidence_scalar(
                "SELECT COALESCE(SUM(record_count), 0) FROM datasets"
            ),
            evidence=self._evidence_scalar("SELECT COUNT(*) FROM edge_evidence"),
            edges=self._runtime_scalar("SELECT COUNT(*) FROM edges"),
            accepted_edges=self._runtime_scalar(
                "SELECT COUNT(*) FROM edges WHERE status='accepted'"
            ),
            conflicts=self._runtime_scalar("SELECT COUNT(*) FROM conflicts"),
        )

        runtime_values = {
            "built_at": built_at,
            "schema_version": str(SCHEMA_VERSION),
            "database_role": "runtime",
            "datasets": str(stats.datasets),
            "records": str(stats.records),
            "evidence": str(stats.evidence),
            "edges": str(stats.edges),
            "accepted_edges": str(stats.accepted_edges),
            "conflicts": str(stats.conflicts),
        }
        evidence_values = dict(runtime_values)
        evidence_values["database_role"] = "evidence"
        for key, value in runtime_values.items():
            self.conn.execute(
                "INSERT OR REPLACE INTO metadata(key, value) VALUES(?, ?)",
                (key, value),
            )
        for key, value in evidence_values.items():
            self.evidence_conn.execute(
                "INSERT OR REPLACE INTO metadata(key, value) VALUES(?, ?)",
                (key, value),
            )

        self.conn.execute("ANALYZE")
        self.evidence_conn.execute("ANALYZE")
        self.conn.commit()
        self.evidence_conn.commit()

        runtime_integrity = self.conn.execute("PRAGMA integrity_check").fetchone()
        if not runtime_integrity or runtime_integrity[0] != "ok":
            raise RuntimeError(
                f"mappings.db integrity check failed: {runtime_integrity}"
            )
        evidence_integrity = self.evidence_conn.execute(
            "PRAGMA integrity_check"
        ).fetchone()
        if not evidence_integrity or evidence_integrity[0] != "ok":
            raise RuntimeError(
                f"mapping evidence database integrity check failed: {evidence_integrity}"
            )
        return stats

    def _build_directional_conflicts(self) -> None:
        self.conn.executescript(
            """
            DROP TABLE IF EXISTS temp.accepted_directions;
            CREATE TEMP TABLE accepted_directions (
                source_node INTEGER NOT NULL,
                target_node INTEGER NOT NULL
            );

            INSERT INTO accepted_directions
            SELECT a_node, b_node FROM edges WHERE status='accepted';

            INSERT INTO accepted_directions
            SELECT b_node, a_node FROM edges WHERE status='accepted';

            CREATE INDEX accepted_directions_source_idx
                ON accepted_directions(source_node, target_node);
            """
        )
        read_cursor = self.conn.execute(
            """
            SELECT source_node, target_provider, GROUP_CONCAT(target_id, char(31))
            FROM (
                SELECT DISTINCT
                    d.source_node AS source_node,
                    target.provider AS target_provider,
                    target.external_id AS target_id
                FROM accepted_directions AS d
                JOIN nodes AS target ON target.id=d.target_node
                ORDER BY d.source_node, target.provider, target.external_id
            )
            GROUP BY source_node, target_provider
            HAVING COUNT(*) > 1
            ORDER BY source_node, target_provider
            """
        )
        write_cursor = self.conn.cursor()
        while True:
            row = read_cursor.fetchone()
            if row is None:
                break
            source_node, target_provider, packed = row
            candidates = sorted(
                {value for value in str(packed or "").split(chr(31)) if value}
            )
            write_cursor.execute(
                """
                INSERT OR REPLACE INTO conflicts(
                    source_node, target_provider, candidate_ids_json, reason
                ) VALUES (?, ?, ?, ?)
                """,
                (
                    int(source_node),
                    str(target_provider),
                    json.dumps(candidates, ensure_ascii=False),
                    "multiple accepted target IDs",
                ),
            )
        self.conn.execute("DROP TABLE temp.accepted_directions")
        self.conn.commit()

    def _runtime_scalar(self, query: str) -> int:
        row = self.conn.execute(query).fetchone()
        return int(row[0] if row else 0)

    def _evidence_scalar(self, query: str) -> int:
        row = self.evidence_conn.execute(query).fetchone()
        return int(row[0] if row else 0)

    def close(self) -> None:
        self.evidence_conn.close()
        self.conn.close()

    def __enter__(self) -> "MappingDatabaseBuilder":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()


class MappingDatabase:
    """Read-only runtime mappings database metadata view."""

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

    def metadata(self) -> dict[str, str]:
        if not self.available:
            return {}
        with managed_sqlite_connection(self._connect()) as conn:
            return {
                str(key): str(value)
                for key, value in conn.execute(
                    "SELECT key, value FROM metadata ORDER BY key"
                )
            }
