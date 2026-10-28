#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="$SCRIPT_DIR/.venv/bin/python"

cd "$SCRIPT_DIR"

[[ -x "$PYTHON" ]] || {
    printf '[anime-db-bot check] ERROR: .venv is missing; run scripts/setup.sh first.\n' >&2
    exit 1
}

printf '[anime-db-bot check] Compiling Python sources...\n'
"$PYTHON" -m compileall -q bots core localization mappings search services sources tests
printf '[anime-db-bot check] Running tests...\n'
"$PYTHON" -m unittest discover -s tests -v
