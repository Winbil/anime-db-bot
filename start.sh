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
[[ -f "$SCRIPT_DIR/bot_official.py" ]] || fail "bot_official.py not found."
[[ -f "$SCRIPT_DIR/bot_tgapi.py" ]] || fail "bot_tgapi.py not found."

if tmux has-session -t "$SESSION_NAME" 2>/dev/null; then
    info "Bot is already running in tmux session '$SESSION_NAME'."
    if [[ ! -t 0 ]]; then
        info "Non-interactive shell detected; leaving the running bot untouched."
        info "Attach with: tmux attach -t $SESSION_NAME"
        exit 0
    fi

    printf '[anime-db-bot] Restart the bot? [y/N]: '
    read -r restart_answer
    case "${restart_answer,,}" in
        y|yes|д|да)
            info "Stopping the current bot session..."
            tmux kill-session -t "$SESSION_NAME"
            ;;
        *)
            info "Restart cancelled. The current bot keeps running."
            exit 0
            ;;
    esac
fi

create_venv() {
    info "Creating virtual environment in .venv..."
    rm -rf "$VENV_DIR"
    if ! python3 -m venv "$VENV_DIR"; then
        fail "Could not create venv. On Ubuntu/Debian install python3-venv: sudo apt install python3-venv"
    fi
}

if [[ ! -d "$VENV_DIR" ]]; then
    create_venv
else
    info "Virtual environment already exists."
fi

PYTHON="$VENV_DIR/bin/python"
if [[ ! -x "$PYTHON" ]]; then
    info "Virtual environment is incomplete. Recreating it..."
    create_venv
    PYTHON="$VENV_DIR/bin/python"
fi

if ! "$PYTHON" -m pip --version >/dev/null 2>&1; then
    info "pip is missing from the virtual environment. Trying ensurepip..."
    if ! "$PYTHON" -m ensurepip --upgrade >/dev/null 2>&1; then
        info "Could not bootstrap pip in the existing venv. Recreating it once..."
        create_venv
        PYTHON="$VENV_DIR/bin/python"
        if ! "$PYTHON" -m pip --version >/dev/null 2>&1; then
            fail "pip is unavailable in the venv. On Ubuntu/Debian run: sudo apt update && sudo apt install python3-venv python3-pip, then remove .venv and run ./start.sh again."
        fi
    fi
fi

info "Using Python: $($PYTHON --version 2>&1)"
info "Using pip: $($PYTHON -m pip --version)"

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

TG_API_URL_VALUE="$(sed -n 's/^[[:space:]]*TELEGRAM_BOT_API_URL[[:space:]]*=[[:space:]]*//p' "$SCRIPT_DIR/.env" | tail -n 1 | tr -d '\r')"
if [[ -n "$TG_API_URL_VALUE" ]]; then
    BOT_ENTRYPOINT="$SCRIPT_DIR/bot_tgapi.py"
    BOT_MODE="custom tg-bot-api (extended messages)"
else
    BOT_ENTRYPOINT="$SCRIPT_DIR/bot_official.py"
    BOT_MODE="official Telegram Bot API (safe 3900-char splitting)"
fi

info "Selected Telegram mode: $BOT_MODE"
mkdir -p "$LOG_DIR"

tmux new-session -d \
    -s "$SESSION_NAME" \
    -c "$SCRIPT_DIR" \
    "exec '$PYTHON' '$BOT_ENTRYPOINT' 2>&1 | tee -a '$LOG_FILE'"

sleep 1

if tmux has-session -t "$SESSION_NAME" 2>/dev/null; then
    info "Bot started in tmux session '$SESSION_NAME'."
    info "Mode:   $BOT_MODE"
    info "Attach: tmux attach -t $SESSION_NAME"
    info "Logs:   tail -f '$LOG_FILE'"
else
    printf '\n' >&2
    [[ -f "$LOG_FILE" ]] && tail -n 50 "$LOG_FILE" >&2 || true
    fail "The bot exited immediately. See the log above or $LOG_FILE"
fi
