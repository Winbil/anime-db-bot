#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$SCRIPT_DIR"

command -v python3 >/dev/null 2>&1 || {
    printf '[anime-db-bot mappings] ERROR: python3 is not installed.\n' >&2
    exit 1
}

exec python3 "$SCRIPT_DIR/scripts/project.py" mappings "$@"
