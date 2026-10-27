#!/usr/bin/env bash
set -Eeuo pipefail

SESSION_NAME="${TMUX_SESSION_NAME:-anime-db-bot}"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/.venv"
LOG_DIR="${LOG_DIR:-$SCRIPT_DIR/logs}"
LOG_FILE="$LOG_DIR/bot.log"
BOT_MODULE="bots.telegram.bot"

cd "$SCRIPT_DIR"

info() {
    printf '[anime-db-bot] %s\n' "$*"
}

fail() {
    printf '[anime-db-bot] ERROR: %s\n' "$*" >&2
    exit 1
}

[[ -f "$SCRIPT_DIR/requirements.lock" ]] || fail "requirements.lock not found."
[[ -f "$SCRIPT_DIR/.env.example" ]] || fail ".env.example not found."
command -v python3 >/dev/null 2>&1 || fail "python3 is not installed."
command -v tmux >/dev/null 2>&1 || fail "tmux is not installed. Install it first, for example: sudo apt install tmux"

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

info "Checking and installing locked Python dependencies..."
"$PYTHON" -m pip install --disable-pip-version-check -r "$SCRIPT_DIR/requirements.lock"

info "Checking dependency consistency..."
"$PYTHON" -m pip check

info "Compiling Python sources..."
"$PYTHON" -m compileall -q bots core localization search services sources tests

info "Running regression and wiring tests..."
"$PYTHON" -m unittest discover -s tests -v

if [[ ! -f "$SCRIPT_DIR/.env" ]]; then
    cp "$SCRIPT_DIR/.env.example" "$SCRIPT_DIR/.env"
    info "Created .env from .env.example."
    fail "Add BOT_TOKEN to .env, then run ./start.sh again."
fi

BOT_TOKEN_VALUE="$(sed -n 's/^[[:space:]]*BOT_TOKEN[[:space:]]*=[[:space:]]*//p' "$SCRIPT_DIR/.env" | tail -n 1 | tr -d '\r')"
[[ -n "$BOT_TOKEN_VALUE" ]] || fail "BOT_TOKEN is empty in .env."

MAL_CLIENT_ID_VALUE="$(sed -n 's/^[[:space:]]*MAL_CLIENT_ID[[:space:]]*=[[:space:]]*//p' "$SCRIPT_DIR/.env" | tail -n 1 | tr -d '\r')"
if [[ -z "$MAL_CLIENT_ID_VALUE" ]]; then
    info "MAL_CLIENT_ID is empty: MyAnimeList search and metadata will be unavailable."
    info "Available non-MAL sources can still provide partial search and metadata results."
    info "Optional MAL setup: https://myanimelist.net/apiconfig"
fi

ensure_jikan_container() {
    if ! command -v docker >/dev/null 2>&1 || ! docker compose version >/dev/null 2>&1; then
        info "Docker Compose is unavailable: MAL/Jikan supplements will be unavailable."
        return 0
    fi

    local state
    state="$(docker inspect --format '{{.State.Status}}' anime-db-bot-Jikan 2>/dev/null || true)"
    if [[ "$state" != "running" ]]; then
        info "Starting local MAL/Jikan supplement container..."
        if ! docker compose up -d --build jikan; then
            info "Could not start anime-db-bot-Jikan; the bot will continue with official MAL data only."
            return 0
        fi
        state="$(docker inspect --format '{{.State.Status}}' anime-db-bot-Jikan 2>/dev/null || true)"
    fi

    info "MAL/Jikan supplement: anime-db-bot-Jikan ($state)."
}

ensure_jikan_container

info "Telegram runtime: $BOT_MODULE"
info "Telegram transport is selected from TELEGRAM_BOT_API_URL."
info "Default /anime search: Shikimori + MAL (MyAnimeList) / Jikan + AniList."
info "Multi-source search can expand through confirmed cross-source titles/IDs."
info "Interactive /anime sources: All / MAL (MyAnimeList) / Jikan / Shikimori / AniList."
info "Direct external-ID lookup is source-independent."
info "Metadata sources: Shikimori + AniList + MAL (MyAnimeList) / Jikan."
info "Staff/seiyuu data is loaded lazily when those sections are opened."

mkdir -p "$LOG_DIR"

tmux new-session -d \
    -s "$SESSION_NAME" \
    -c "$SCRIPT_DIR" \
    "exec '$PYTHON' -m '$BOT_MODULE' 2>&1 | tee -a '$LOG_FILE'"

sleep 1

if tmux has-session -t "$SESSION_NAME" 2>/dev/null; then
    info "Bot started in tmux session '$SESSION_NAME'."
    info "Module:  $BOT_MODULE"
    info "Attach:  tmux attach -t $SESSION_NAME"
    info "Logs:    tail -f '$LOG_FILE'"
else
    printf '\n' >&2
    [[ -f "$LOG_FILE" ]] && tail -n 50 "$LOG_FILE" >&2 || true
    fail "The bot exited immediately. See the log above or $LOG_FILE"
fi