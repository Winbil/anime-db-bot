#!/usr/bin/env bash
set -Eeuo pipefail

SESSION_NAME="${TMUX_SESSION_NAME:-anime-db-bot}"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/.venv"
LOG_DIR="${LOG_DIR:-$SCRIPT_DIR/logs}"
LOG_FILE="$LOG_DIR/bot.log"

cd "$SCRIPT_DIR"

info() {
    printf '[anime-db-bot] %s\n' "$*"
}

fail() {
    printf '[anime-db-bot] ERROR: %s\n' "$*" >&2
    exit 1
}

command -v python3 >/dev/null 2>&1 || fail "python3 is not installed."
command -v tmux >/dev/null 2>&1 || fail "tmux is not installed. Install it first, for example: sudo apt install tmux"
[[ -f "$SCRIPT_DIR/requirements.txt" ]] || fail "requirements.txt not found."
[[ -f "$SCRIPT_DIR/bot.py" ]] || fail "bot.py not found."

if [[ ! -d "$VENV_DIR" ]]; then
    info "Creating virtual environment in .venv..."
    if ! python3 -m venv "$VENV_DIR"; then
        fail "Could not create venv. On Ubuntu/Debian install python3-venv: sudo apt install python3-venv"
    fi
else
    info "Virtual environment already exists."
fi

PYTHON="$VENV_DIR/bin/python"
[[ -x "$PYTHON" ]] || fail "Virtual environment is incomplete: $PYTHON is missing. Remove .venv and run this script again."

info "Checking and installing Python dependencies..."
"$PYTHON" -m pip install --disable-pip-version-check -r "$SCRIPT_DIR/requirements.txt"

info "Checking dependency consistency..."
"$PYTHON" -m pip check

info "Checking required imports..."
"$PYTHON" - <<'PY'
import aiogram
import httpx
import dotenv
print("Python imports: OK")
PY

if [[ ! -f "$SCRIPT_DIR/.env" ]]; then
    [[ -f "$SCRIPT_DIR/.env.example" ]] || fail ".env and .env.example are both missing."
    cp "$SCRIPT_DIR/.env.example" "$SCRIPT_DIR/.env"
    info "Created .env from .env.example."
    fail "Add BOT_TOKEN to .env, then run ./start.sh again."
fi

BOT_TOKEN_VALUE="$(sed -n 's/^[[:space:]]*BOT_TOKEN[[:space:]]*=[[:space:]]*//p' "$SCRIPT_DIR/.env" | tail -n 1 | tr -d '\r')"
[[ -n "$BOT_TOKEN_VALUE" ]] || fail "BOT_TOKEN is empty in .env."

if tmux has-session -t "$SESSION_NAME" 2>/dev/null; then
    info "tmux session '$SESSION_NAME' is already running."
    info "Attach with: tmux attach -t $SESSION_NAME"
    exit 0
fi

mkdir -p "$LOG_DIR"

tmux new-session -d \
    -s "$SESSION_NAME" \
    -c "$SCRIPT_DIR" \
    "exec '$PYTHON' '$SCRIPT_DIR/bot.py' 2>&1 | tee -a '$LOG_FILE'"

sleep 1

if tmux has-session -t "$SESSION_NAME" 2>/dev/null; then
    info "Bot started in tmux session '$SESSION_NAME'."
    info "Attach: tmux attach -t $SESSION_NAME"
    info "Logs:   tail -f '$LOG_FILE'"
else
    printf '\n' >&2
    [[ -f "$LOG_FILE" ]] && tail -n 50 "$LOG_FILE" >&2 || true
    fail "The bot exited immediately. See the log above or $LOG_FILE"
fi
