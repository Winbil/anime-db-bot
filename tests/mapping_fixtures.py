from __future__ import annotations

import json
import sqlite3
from pathlib import Path


def create_runtime_mapping_db(
    path: Path,
    edges: list[tuple[str, str, str, str]],
    *,
    conflicts: list[tuple[str, str, str, list[str]]] | None = None,
    anchors: dict[tuple[str, str], int] | None = None,
    redirects: dict[int, int] | None = None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.unlink(missing_ok=True)
    connection = sqlite3.connect(path)
    try:
        connection.executescript(
            """
            CREATE TABLE metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE nodes(
                id INTEGER PRIMARY KEY,
                provider TEXT NOT NULL,
                external_id TEXT NOT NULL,
                UNIQUE(provider, external_id)
            );
            CREATE TABLE edges(
                a_node INTEGER NOT NULL,
                b_node INTEGER NOT NULL,
                confidence INTEGER NOT NULL,
                status TEXT NOT NULL,
                evidence_count INTEGER NOT NULL,
                evidence_group_count INTEGER NOT NULL,
                max_weight INTEGER NOT NULL,
                PRIMARY KEY(a_node, b_node)
            ) WITHOUT ROWID;
            CREATE INDEX edges_a_lookup_idx ON edges(a_node, status, b_node);
            CREATE INDEX edges_b_lookup_idx ON edges(b_node, status, a_node);
            CREATE TABLE conflicts(
                source_node INTEGER NOT NULL,
                target_provider TEXT NOT NULL,
                candidate_ids_json TEXT NOT NULL,
                reason TEXT NOT NULL,
                PRIMARY KEY(source_node, target_provider)
            ) WITHOUT ROWID;
            CREATE TABLE mapping_overrides(
                source_provider TEXT NOT NULL,
                source_id TEXT NOT NULL,
                target_provider TEXT NOT NULL,
                target_id TEXT NOT NULL,
                action TEXT NOT NULL CHECK(action IN ('accept', 'reject')),
                reason TEXT NOT NULL DEFAULT '',
                author TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL DEFAULT '',
                PRIMARY KEY(source_provider, source_id, target_provider, target_id)
            ) WITHOUT ROWID;
            CREATE TABLE mapping_override_history(
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
        node_ids: dict[tuple[str, str], int] = {}

        def node_id(provider: str, external_id: str) -> int:
            key = (provider, external_id)
            existing = node_ids.get(key)
            if existing is not None:
                return existing
            cursor = connection.execute(
                "INSERT INTO nodes(provider, external_id) VALUES (?, ?)", key
            )
            value = int(cursor.lastrowid)
            node_ids[key] = value
            return value

        for a_provider, a_id, b_provider, b_id in edges:
            a_node = node_id(a_provider, a_id)
            b_node = node_id(b_provider, b_id)
            left, right = sorted((a_node, b_node))
            connection.execute(
                """
                INSERT OR REPLACE INTO edges(
                    a_node, b_node, confidence, status, evidence_count,
                    evidence_group_count, max_weight
                ) VALUES (?, ?, 95, 'accepted', 1, 1, 95)
                """,
                (left, right),
            )

        for source_provider, source_id, target_provider, candidates in conflicts or []:
            source_node = node_id(source_provider, source_id)
            connection.execute(
                """
                INSERT INTO conflicts(
                    source_node, target_provider, candidate_ids_json, reason
                ) VALUES (?, ?, ?, 'multiple accepted target IDs')
                """,
                (
                    source_node,
                    target_provider,
                    json.dumps(sorted(candidates), ensure_ascii=False),
                ),
            )

        if anchors is not None:
            connection.executescript(
                """
                CREATE TABLE entities(
                    entity_id INTEGER PRIMARY KEY,
                    anchor_id INTEGER NOT NULL UNIQUE
                );
                CREATE TABLE entity_nodes(
                    entity_id INTEGER NOT NULL,
                    node_id INTEGER NOT NULL,
                    PRIMARY KEY(entity_id, node_id)
                ) WITHOUT ROWID;
                CREATE TABLE anchor_redirects(
                    old_anchor_id INTEGER PRIMARY KEY,
                    anchor_id INTEGER NOT NULL,
                    reason TEXT NOT NULL DEFAULT 'merged'
                );
                """
            )
            for anchor_id in sorted(set(anchors.values())):
                connection.execute(
                    "INSERT INTO entities(entity_id, anchor_id) VALUES (?, ?)",
                    (anchor_id, anchor_id),
                )
            for (provider, external_id), anchor_id in anchors.items():
                connection.execute(
                    "INSERT INTO entity_nodes(entity_id, node_id) VALUES (?, ?)",
                    (anchor_id, node_id(provider, external_id)),
                )
            for previous, current in (redirects or {}).items():
                connection.execute(
                    "INSERT INTO anchor_redirects(old_anchor_id, anchor_id) VALUES (?, ?)",
                    (previous, current),
                )

        counts = {
            "schema_version": "3",
            "database_role": "runtime",
            "datasets": "1",
            "records": str(max(1, len(edges))),
            "evidence": str(max(1, len(edges))),
            "edges": str(len(edges)),
            "accepted_edges": str(len(edges)),
            "conflicts": str(len(conflicts or [])),
            "overrides": "0",
            "built_at": "2026-11-01T00:00:00+00:00",
        }
        connection.executemany(
            "INSERT INTO metadata(key, value) VALUES (?, ?)", counts.items()
        )
        connection.commit()
    finally:
        connection.close()
