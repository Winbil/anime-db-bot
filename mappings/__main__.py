from __future__ import annotations

import argparse
import json
import logging

from mappings.config import mappings_auto_update
from mappings.updater import mapping_status, update_mapping_database, update_if_stale


def main() -> None:
    parser = argparse.ArgumentParser(description="Build and inspect mappings.db")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--force", action="store_true", help="rebuild even when the DB is fresh")
    group.add_argument("--status", action="store_true", help="print DB status without updating")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
    if args.status:
        print(json.dumps(mapping_status(), ensure_ascii=False, indent=2, sort_keys=True))
        return

    if args.force:
        stats = update_mapping_database(force=True)
    elif mappings_auto_update():
        stats = update_if_stale()
    else:
        stats = None

    if stats is None:
        print(json.dumps(mapping_status(), ensure_ascii=False, indent=2, sort_keys=True))
        return
    print(json.dumps({
        "datasets": stats.datasets,
        "records": stats.records,
        "evidence": stats.evidence,
        "edges": stats.edges,
        "accepted_edges": stats.accepted_edges,
        "conflicts": stats.conflicts,
    }, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
