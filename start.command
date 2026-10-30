#!/bin/sh
set -eu

ROOT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$ROOT_DIR"

if command -v python3 >/dev/null 2>&1; then
    exec python3 "$ROOT_DIR/scripts/project.py" start "$@"
fi

echo "[anime-db-bot] ERROR: Python 3.11-3.14 is required." >&2
exit 1
