#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="$SCRIPT_DIR/.venv"
PYTHON="$VENV_DIR/bin/python"

cd "$SCRIPT_DIR"

info() {
    printf '[anime-db-bot setup] %s\n' "$*"
}

fail() {
    printf '[anime-db-bot setup] ERROR: %s\n' "$*" >&2
    exit 1
}

[[ -f "$SCRIPT_DIR/requirements.lock" ]] || fail "requirements.lock not found."
command -v python3 >/dev/null 2>&1 || fail "python3 is not installed."

create_venv() {
    info "Creating virtual environment in .venv..."
    rm -rf "$VENV_DIR"
    if ! python3 -m venv "$VENV_DIR"; then
        fail "Could not create venv. On Ubuntu/Debian install python3-venv."
    fi
}

if [[ ! -x "$PYTHON" ]]; then
    create_venv
fi

if ! "$PYTHON" -m pip --version >/dev/null 2>&1; then
    info "pip is missing; trying ensurepip..."
    if ! "$PYTHON" -m ensurepip --upgrade >/dev/null 2>&1; then
        create_venv
    fi
fi

"$PYTHON" -m pip --version >/dev/null 2>&1 || fail "pip is unavailable in .venv."
info "Installing locked dependencies..."
"$PYTHON" -m pip install --disable-pip-version-check -r "$SCRIPT_DIR/requirements.lock"
info "Checking dependency consistency..."
"$PYTHON" -m pip check
info "Environment is ready: $($PYTHON --version 2>&1)"
