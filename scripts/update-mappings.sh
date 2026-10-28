#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="$SCRIPT_DIR/.venv/bin/python"

cd "$SCRIPT_DIR"

[[ -x "$PYTHON" ]] || {
    printf '[anime-db-bot mappings] ERROR: .venv is missing; run scripts/setup.sh first.\n' >&2
    exit 1
}

exec "$PYTHON" -m mappings "$@"
