from __future__ import annotations

import argparse
import json

from core.logging_config import configure_logging
from mappings.config import mappings_auto_update
from mappings.resolver import (
    delete_mapping_override,
    list_mapping_override_history,
    list_mapping_overrides,
    set_mapping_override,
)
from mappings.updater import mapping_status, update_mapping_database, update_if_stale


def _override_dict(override: object) -> dict[str, str]:
    return {
        "source_provider": str(getattr(override, "source_provider")),
        "source_id": str(getattr(override, "source_id")),
        "target_provider": str(getattr(override, "target_provider")),
        "target_id": str(getattr(override, "target_id")),
        "action": str(getattr(override, "action")),
        "reason": str(getattr(override, "reason")),
        "author": str(getattr(override, "author", "")),
        "updated_at": str(getattr(override, "updated_at", "")),
    }


def _history_dict(item: object) -> dict[str, str]:
    return {
        "source_provider": str(getattr(item, "source_provider")),
        "source_id": str(getattr(item, "source_id")),
        "target_provider": str(getattr(item, "target_provider")),
        "target_id": str(getattr(item, "target_id")),
        "event": str(getattr(item, "event")),
        "override_action": str(getattr(item, "override_action")),
        "reason": str(getattr(item, "reason")),
        "author": str(getattr(item, "author")),
        "changed_at": str(getattr(item, "changed_at")),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build and inspect mappings.db")
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--force", action="store_true", help="rebuild even when the DB is fresh"
    )
    group.add_argument(
        "--status", action="store_true", help="print DB status without updating"
    )
    group.add_argument(
        "--override-history",
        action="store_true",
        help="list mapping override audit history",
    )
    group.add_argument(
        "--override-list",
        action="store_true",
        help="list directional manual mapping overrides",
    )
    group.add_argument(
        "--override-set",
        nargs=5,
        metavar=("ACTION", "SOURCE", "SOURCE_ID", "TARGET", "TARGET_ID"),
        help="set directional accept/reject override; requires --reason",
    )
    group.add_argument(
        "--override-delete",
        nargs=4,
        metavar=("SOURCE", "SOURCE_ID", "TARGET", "TARGET_ID"),
        help="delete one directional manual override",
    )
    parser.add_argument(
        "--reason", default="", help="audit reason for override changes"
    )
    parser.add_argument(
        "--author", default="cli", help="audit author for override changes"
    )
    args = parser.parse_args()

    configure_logging(level="INFO", structured=False)

    if args.override_history:
        print(
            json.dumps(
                [_history_dict(item) for item in list_mapping_override_history()],
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
        )
        return

    if args.override_list:
        print(
            json.dumps(
                [_override_dict(item) for item in list_mapping_overrides()],
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
        )
        return

    if args.override_set:
        action, source, source_id, target, target_id = args.override_set
        override = set_mapping_override(
            source,
            source_id,
            target,
            target_id,
            action=action,
            reason=args.reason,
            author=args.author,
        )
        print(
            json.dumps(
                _override_dict(override),
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
        )
        return

    if args.override_delete:
        source, source_id, target, target_id = args.override_delete
        removed = delete_mapping_override(
            source,
            source_id,
            target,
            target_id,
            reason=args.reason or "manual override deleted",
            author=args.author,
        )
        print(json.dumps({"removed": removed}, ensure_ascii=False, indent=2))
        return

    if args.status:
        print(
            json.dumps(mapping_status(), ensure_ascii=False, indent=2, sort_keys=True)
        )
        return

    if args.force:
        stats = update_mapping_database(force=True)
    elif mappings_auto_update():
        stats = update_if_stale()
    else:
        stats = None

    if stats is None:
        print(
            json.dumps(mapping_status(), ensure_ascii=False, indent=2, sort_keys=True)
        )
        return
    print(
        json.dumps(
            {
                "datasets": stats.datasets,
                "records": stats.records,
                "evidence": stats.evidence,
                "edges": stats.edges,
                "accepted_edges": stats.accepted_edges,
                "conflicts": stats.conflicts,
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
