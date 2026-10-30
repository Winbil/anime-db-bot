from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from core.sqlite import managed_sqlite_connection
from mappings.config import MappingSourceSpec, mappings_db_path

SCHEMA_VERSION = 2


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


def _canonical_edge(
    left_provider: str,
    left_id: str,
    right_provider: str,
    right_id: str,
) -> tuple[str, str, str, str]:
    left = (left_provider, left_id)
    right = (right_provider, right_id)
    if right < left:
        left, right = right, left
    return left[0], left[1], right[0], right[1]


class MappingDatabaseBuilder:
    """Incrementally build a disk-backed cross-ID evidence graph.

    The builder intentionally never materializes a source dataset or a global ID
    index in Python memory. Importers yield one record at a time; evidence and all
    lookup indexes are persisted directly in SQLite.
    """

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists():
            self.path.unlink()
        self.conn = sqlite3.connect(self.path)
        self.conn.execute("PRAGMA journal_mode=OFF")
        self.conn.execute("PRAGMA synchronous=OFF")
        self.conn.execute("PRAGMA temp_store=FILE")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self._create_schema()

    def _create_schema(self) -> None:
        self.conn.executescript(
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

            CREATE TABLE edge_evidence (
                dataset_id INTEGER NOT NULL REFERENCES datasets(id) ON DELETE CASCADE,
                record_key TEXT NOT NULL,
                evidence_group TEXT NOT NULL,
                weight INTEGER NOT NULL,
                a_provider TEXT NOT NULL,
                a_id TEXT NOT NULL,
                b_provider TEXT NOT NULL,
                b_id TEXT NOT NULL,
                PRIMARY KEY (
                    dataset_id, record_key, evidence_group,
                    a_provider, a_id, b_provider, b_id
                )
            ) WITHOUT ROWID;

            CREATE INDEX edge_evidence_a_idx
                ON edge_evidence(a_provider, a_id, b_provider);
            CREATE INDEX edge_evidence_b_idx
                ON edge_evidence(b_provider, b_id, a_provider);

            CREATE TABLE edges (
                a_provider TEXT NOT NULL,
                a_id TEXT NOT NULL,
                b_provider TEXT NOT NULL,
                b_id TEXT NOT NULL,
                confidence INTEGER NOT NULL,
                status TEXT NOT NULL,
                evidence_count INTEGER NOT NULL,
                evidence_group_count INTEGER NOT NULL,
                max_weight INTEGER NOT NULL,
                PRIMARY KEY (a_provider, a_id, b_provider, b_id)
            ) WITHOUT ROWID;

            CREATE INDEX edges_a_lookup_idx
                ON edges(a_provider, a_id, status, b_provider);
            CREATE INDEX edges_b_lookup_idx
                ON edges(b_provider, b_id, status, a_provider);

            CREATE TABLE conflicts (
                source_provider TEXT NOT NULL,
                source_id TEXT NOT NULL,
                target_provider TEXT NOT NULL,
                candidate_ids_json TEXT NOT NULL,
                reason TEXT NOT NULL,
                PRIMARY KEY (source_provider, source_id, target_provider)
            ) WITHOUT ROWID;

            CREATE INDEX conflicts_lookup_idx
                ON conflicts(source_provider, source_id, target_provider);

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
        self.conn.execute(
            "INSERT INTO metadata(key, value) VALUES('schema_version', ?)",
            (str(SCHEMA_VERSION),),
        )
        self.conn.commit()

    def ingest_dataset(
        self,
        spec: MappingSourceSpec,
        records: Iterable[MappingRecord],
        *,
        sha256: str,
        downloaded_at: str,
    ) -> int:
        cursor = self.conn.execute(
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
                self.conn.commit()

        self.conn.execute(
            "UPDATE datasets SET record_count=? WHERE id=?",
            (record_count, dataset_id),
        )
        self.conn.commit()
        return record_count

    def _insert_record(self, dataset_id: int, record: MappingRecord) -> bool:
        nodes: list[tuple[str, str]] = []
        seen: set[tuple[str, str]] = set()
        for raw_provider, raw_values in record.ids.items():
            provider = _clean_provider(raw_provider)
            if not provider:
                continue
            for raw_id in raw_values:
                external_id = _clean_id(raw_id)
                node = (provider, external_id)
                if external_id and node not in seen:
                    seen.add(node)
                    nodes.append(node)

        if len({provider for provider, _ in nodes}) < 2:
            return False

        inserted = False
        for left_index, (left_provider, left_id) in enumerate(nodes):
            for right_provider, right_id in nodes[left_index + 1 :]:
                if left_provider == right_provider:
                    continue
                a_provider, a_id, b_provider, b_id = _canonical_edge(
                    left_provider,
                    left_id,
                    right_provider,
                    right_id,
                )
                self.conn.execute(
                    """
                    INSERT OR IGNORE INTO edge_evidence(
                        dataset_id, record_key, evidence_group, weight,
                        a_provider, a_id, b_provider, b_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        dataset_id,
                        record.record_key,
                        record.evidence_group,
                        max(0, min(int(record.weight), 100)),
                        a_provider,
                        a_id,
                        b_provider,
                        b_id,
                    ),
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
        """Copy one already-normalized dataset into a new atomic rebuild.

        This lets source-specific refresh intervals coexist: datasets that are not
        due for a network check keep their existing evidence without being
        downloaded again.
        """

        source_path = Path(source_path)
        if not source_path.is_file():
            return 0
        uri = f"file:{source_path.resolve().as_posix()}?mode=ro"
        try:
            with managed_sqlite_connection(
                sqlite3.connect(uri, uri=True, timeout=5.0)
            ) as source:
                source.execute("PRAGMA query_only=ON")
                row = source.execute(
                    """
                    SELECT id, source_url, importer, license_note, sha256,
                           downloaded_at, record_count
                    FROM datasets WHERE name=?
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
                cursor = self.conn.execute(
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
                read_cursor = source.execute(
                    """
                    SELECT record_key, evidence_group, weight,
                           a_provider, a_id, b_provider, b_id
                    FROM edge_evidence WHERE dataset_id=?
                    """,
                    (source_dataset_id,),
                )
                while True:
                    rows = read_cursor.fetchmany(5000)
                    if not rows:
                        break
                    self.conn.executemany(
                        """
                        INSERT INTO edge_evidence(
                            dataset_id, record_key, evidence_group, weight,
                            a_provider, a_id, b_provider, b_id
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        [(destination_dataset_id, *evidence) for evidence in rows],
                    )
                    self.conn.commit()
                self.conn.commit()
                return int(record_count or 0)
        except sqlite3.OperationalError:
            return 0

    def finalize(self, *, built_at: str) -> MappingBuildStats:
        self.conn.execute("DELETE FROM edges")
        self.conn.execute("DELETE FROM conflicts")
        self.conn.execute(
            """
            INSERT INTO edges(
                a_provider, a_id, b_provider, b_id,
                confidence, status, evidence_count,
                evidence_group_count, max_weight
            )
            SELECT
                a_provider,
                a_id,
                b_provider,
                b_id,
                MIN(
                    100,
                    MAX(weight)
                    + 8 * (COUNT(DISTINCT evidence_group) - 1)
                    + 2 * MIN(
                        5,
                        COUNT(*) - COUNT(DISTINCT evidence_group)
                    )
                ) AS confidence,
                CASE
                    WHEN MAX(weight) >= 80
                         OR COUNT(DISTINCT evidence_group) >= 2
                    THEN 'accepted'
                    ELSE 'candidate'
                END AS status,
                COUNT(*) AS evidence_count,
                COUNT(DISTINCT evidence_group) AS evidence_group_count,
                MAX(weight) AS max_weight
            FROM edge_evidence
            GROUP BY a_provider, a_id, b_provider, b_id
            """
        )
        self.conn.commit()
        self._build_directional_conflicts()

        values = {
            "built_at": built_at,
            "schema_version": str(SCHEMA_VERSION),
        }
        for key, value in values.items():
            self.conn.execute(
                "INSERT OR REPLACE INTO metadata(key, value) VALUES(?, ?)",
                (key, value),
            )

        self.conn.execute("ANALYZE")
        self.conn.commit()
        integrity = self.conn.execute("PRAGMA integrity_check").fetchone()
        if not integrity or integrity[0] != "ok":
            raise RuntimeError(f"mappings.db integrity check failed: {integrity}")

        stats = MappingBuildStats(
            datasets=self._scalar("SELECT COUNT(*) FROM datasets"),
            records=self._scalar("SELECT COALESCE(SUM(record_count), 0) FROM datasets"),
            evidence=self._scalar("SELECT COUNT(*) FROM edge_evidence"),
            edges=self._scalar("SELECT COUNT(*) FROM edges"),
            accepted_edges=self._scalar(
                "SELECT COUNT(*) FROM edges WHERE status='accepted'"
            ),
            conflicts=self._scalar("SELECT COUNT(*) FROM conflicts"),
        )
        for key, metric_value in {
            "datasets": stats.datasets,
            "records": stats.records,
            "evidence": stats.evidence,
            "edges": stats.edges,
            "accepted_edges": stats.accepted_edges,
            "conflicts": stats.conflicts,
        }.items():
            self.conn.execute(
                "INSERT OR REPLACE INTO metadata(key, value) VALUES(?, ?)",
                (key, str(metric_value)),
            )
        self.conn.commit()
        return stats

    def _build_directional_conflicts(self) -> None:
        self.conn.executescript(
            """
            DROP TABLE IF EXISTS temp.accepted_directions;
            CREATE TEMP TABLE accepted_directions (
                source_provider TEXT NOT NULL,
                source_id TEXT NOT NULL,
                target_provider TEXT NOT NULL,
                target_id TEXT NOT NULL
            );

            INSERT INTO accepted_directions
            SELECT a_provider, a_id, b_provider, b_id
            FROM edges WHERE status='accepted';

            INSERT INTO accepted_directions
            SELECT b_provider, b_id, a_provider, a_id
            FROM edges WHERE status='accepted';

            CREATE INDEX accepted_directions_source_idx
                ON accepted_directions(source_provider, source_id, target_provider);
            """
        )
        read_cursor = self.conn.execute(
            """
            SELECT source_provider, source_id, target_provider,
                   GROUP_CONCAT(target_id, char(31))
            FROM (
                SELECT DISTINCT
                    source_provider, source_id, target_provider, target_id
                FROM accepted_directions
            )
            GROUP BY source_provider, source_id, target_provider
            HAVING COUNT(*) > 1
            ORDER BY source_provider, source_id, target_provider
            """
        )
        write_cursor = self.conn.cursor()
        while True:
            row = read_cursor.fetchone()
            if row is None:
                break
            provider, external_id, target_provider, packed = row
            candidates = sorted(
                {value for value in str(packed or "").split(chr(31)) if value}
            )
            write_cursor.execute(
                """
                INSERT OR REPLACE INTO conflicts(
                    source_provider, source_id, target_provider,
                    candidate_ids_json, reason
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    provider,
                    external_id,
                    target_provider,
                    json.dumps(candidates, ensure_ascii=False),
                    "multiple accepted target IDs",
                ),
            )
        self.conn.execute("DROP TABLE temp.accepted_directions")
        self.conn.commit()

    def _scalar(self, query: str) -> int:
        row = self.conn.execute(query).fetchone()
        return int(row[0] if row else 0)

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "MappingDatabaseBuilder":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()


class MappingDatabase:
    """Read-only mappings database metadata view.

    Runtime cross-ID enrichment deliberately lives in :mod:`mappings.resolver`.
    Keeping resolution out of this low-level database wrapper prevents accidental
    reintroduction of arbitrary recursive graph traversal.
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
