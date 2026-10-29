#!/usr/bin/env bash
set -Eeuo pipefail

SESSION_NAME="${TMUX_SESSION_NAME:-anime-db-bot}"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/.venv"
LOG_DIR="${LOG_DIR:-$SCRIPT_DIR/logs}"
LOG_FILE="$LOG_DIR/bot.log"
LOG_MAX_BYTES="${LOG_MAX_BYTES:-}"
LOG_BACKUPS="${LOG_BACKUPS:-}"
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
        y|yes)
            info "Stopping the current bot session..."
            tmux kill-session -t "$SESSION_NAME"
            ;;
        *)
            info "Restart cancelled. The current bot keeps running."
            exit 0
            ;;
    esac
fi

PYTHON="$VENV_DIR/bin/python"
if [[ ! -x "$PYTHON" ]] || ! "$PYTHON" -m pip --version >/dev/null 2>&1; then
    info "Python environment is missing or incomplete; running scripts/setup.sh..."
    "$SCRIPT_DIR/scripts/setup.sh"
fi

PYTHON="$VENV_DIR/bin/python"
[[ -x "$PYTHON" ]] || fail "Virtual environment is unavailable after setup."

info "Using Python: $($PYTHON --version 2>&1)"

if [[ ! -f "$SCRIPT_DIR/.env" ]]; then
    cp "$SCRIPT_DIR/.env.example" "$SCRIPT_DIR/.env"
    info "Created .env from .env.example."
    fail "Add BOT_TOKEN to .env, then run ./start.sh again."
fi

if [[ -z "$LOG_MAX_BYTES" ]]; then
    LOG_MAX_BYTES="$(sed -n 's/^[[:space:]]*LOG_MAX_BYTES[[:space:]]*=[[:space:]]*//p' "$SCRIPT_DIR/.env" | tail -n 1 | tr -d '\r')"
fi
if [[ -z "$LOG_BACKUPS" ]]; then
    LOG_BACKUPS="$(sed -n 's/^[[:space:]]*LOG_BACKUPS[[:space:]]*=[[:space:]]*//p' "$SCRIPT_DIR/.env" | tail -n 1 | tr -d '\r')"
fi
LOG_MAX_BYTES="${LOG_MAX_BYTES:-10485760}"
LOG_BACKUPS="${LOG_BACKUPS:-5}"
[[ "$LOG_MAX_BYTES" =~ ^[1-9][0-9]*$ ]] || fail "LOG_MAX_BYTES must be a positive integer."
[[ "$LOG_BACKUPS" =~ ^[0-9]+$ ]] || fail "LOG_BACKUPS must be a non-negative integer."

BOT_TOKEN_VALUE="$(sed -n 's/^[[:space:]]*BOT_TOKEN[[:space:]]*=[[:space:]]*//p' "$SCRIPT_DIR/.env" | tail -n 1 | tr -d '\r')"
[[ -n "$BOT_TOKEN_VALUE" ]] || fail "BOT_TOKEN is empty in .env."

MAL_CLIENT_ID_VALUE="$(sed -n 's/^[[:space:]]*MAL_CLIENT_ID[[:space:]]*=[[:space:]]*//p' "$SCRIPT_DIR/.env" | tail -n 1 | tr -d '\r')"
if [[ -z "$MAL_CLIENT_ID_VALUE" ]]; then
    info "MAL_CLIENT_ID is empty: MyAnimeList search and metadata will be unavailable."
    info "Available non-MAL sources can still provide partial search and metadata results."
fi

ANIDB_CLIENT_VALUE="$(sed -n 's/^[[:space:]]*ANIDB_CLIENT[[:space:]]*=[[:space:]]*//p' "$SCRIPT_DIR/.env" | tail -n 1 | tr -d '\r')"
if [[ -z "$ANIDB_CLIENT_VALUE" ]]; then
    info "ANIDB_CLIENT is empty: AniDB HTTP metadata is disabled; mappings.db can still resolve AniDB IDs."
else
    info "AniDB HTTP metadata source is configured."
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
info "External IDs are enriched locally from disk-backed mappings.db."
info "Interactive /anime sources: All / MAL (MyAnimeList) / Jikan / Shikimori / AniList."
info "Direct external-ID lookup is source-independent."
info "Metadata sources: Shikimori + AniList + MAL (MyAnimeList) / Jikan + optional AniDB."
info "Staff/seiyuu/characters and episode backends are loaded lazily."
info "Use scripts/check.sh for compile/tests and scripts/update-mappings.sh for an explicit mapping refresh."

mkdir -p "$LOG_DIR"

rotate_log_if_needed() {
    [[ -f "$LOG_FILE" ]] || return 0
    local current_size
    current_size="$(wc -c < "$LOG_FILE")"
    (( current_size < LOG_MAX_BYTES )) && return 0

    if (( LOG_BACKUPS == 0 )); then
        : > "$LOG_FILE"
        info "Truncated bot log after reaching ${LOG_MAX_BYTES} bytes."
        return 0
    fi

    local index
    for (( index=LOG_BACKUPS; index>=2; index-- )); do
        if [[ -f "$LOG_FILE.$((index - 1))" ]]; then
            mv -f "$LOG_FILE.$((index - 1))" "$LOG_FILE.$index"
        fi
    done
    mv -f "$LOG_FILE" "$LOG_FILE.1"
    info "Rotated bot log after reaching ${LOG_MAX_BYTES} bytes; keeping ${LOG_BACKUPS} backup(s)."
}

rotate_log_if_needed

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
    if [[ -f "$LOG_FILE" ]]; then
        tail -n 50 "$LOG_FILE" >&2
    fi
    fail "The bot exited immediately. See the log above or $LOG_FILE"
fi
