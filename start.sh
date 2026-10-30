#!/usr/bin/env bash
set -Eeuo pipefail

SESSION_NAME="${TMUX_SESSION_NAME:-anime-db-bot}"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/.venv"
LOG_DIR="${LOG_DIR:-}"
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
[[ -d "$SCRIPT_DIR/.env.example.d" ]] || fail ".env.example.d not found."
ENV_FILES=(telegram.env sources.env timestamps.env rate-limits.env mappings.env storage.env logging.env runtime.env)
PROXY_FILES=(telegram.toml shikimori.toml mal.toml anilist.toml kitsu.toml anidb.toml anisearch.toml jikan.toml aniskip.toml anime_skip.toml bahamut.toml baha_anime_skip.toml skipdb.toml trace_moe.toml whatanimeisthis.toml)
USER_AGENT_FILES=(telegram.toml shikimori.toml mal.toml anilist.toml kitsu.toml anidb.toml anisearch.toml jikan.toml aniskip.toml anime_skip.toml bahamut.toml baha_anime_skip.toml skipdb.toml trace_moe.toml whatanimeisthis.toml)
for env_name in "${ENV_FILES[@]}"; do
    [[ -f "$SCRIPT_DIR/.env.example.d/$env_name" ]] || fail ".env.example.d/$env_name not found."
done
[[ -d "$SCRIPT_DIR/.proxies.example.d" ]] || fail ".proxies.example.d not found."
for proxy_name in "${PROXY_FILES[@]}"; do
    [[ -f "$SCRIPT_DIR/.proxies.example.d/$proxy_name" ]] || fail ".proxies.example.d/$proxy_name not found."
done
[[ -d "$SCRIPT_DIR/.user-agents.example.d" ]] || fail ".user-agents.example.d not found."
for user_agent_name in "${USER_AGENT_FILES[@]}"; do
    [[ -f "$SCRIPT_DIR/.user-agents.example.d/$user_agent_name" ]] || fail ".user-agents.example.d/$user_agent_name not found."
done
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

if [[ ! -d "$SCRIPT_DIR/.proxies.d" ]]; then
    mkdir -m 700 "$SCRIPT_DIR/.proxies.d"
    info "Created .proxies.d from .proxies.example.d (all proxy entries disabled by default)."
fi
chmod 700 "$SCRIPT_DIR/.proxies.d"
for proxy_name in "${PROXY_FILES[@]}"; do
    if [[ ! -f "$SCRIPT_DIR/.proxies.d/$proxy_name" ]]; then
        cp "$SCRIPT_DIR/.proxies.example.d/$proxy_name" "$SCRIPT_DIR/.proxies.d/$proxy_name"
    fi
    chmod 600 "$SCRIPT_DIR/.proxies.d/$proxy_name"
done

if [[ ! -d "$SCRIPT_DIR/.user-agents.d" ]]; then
    mkdir -m 700 "$SCRIPT_DIR/.user-agents.d"
    info "Created .user-agents.d from .user-agents.example.d (built-in anime-db-bot UA remains the default)."
fi
chmod 700 "$SCRIPT_DIR/.user-agents.d"
for user_agent_name in "${USER_AGENT_FILES[@]}"; do
    if [[ ! -f "$SCRIPT_DIR/.user-agents.d/$user_agent_name" ]]; then
        cp "$SCRIPT_DIR/.user-agents.example.d/$user_agent_name" "$SCRIPT_DIR/.user-agents.d/$user_agent_name"
    fi
    chmod 600 "$SCRIPT_DIR/.user-agents.d/$user_agent_name"
done

HAS_SPLIT_CONFIG=0
for env_name in "${ENV_FILES[@]}"; do
    if [[ -f "$SCRIPT_DIR/.env.d/$env_name" ]]; then
        HAS_SPLIT_CONFIG=1
        break
    fi
done

if [[ ! -f "$SCRIPT_DIR/.env" && "$HAS_SPLIT_CONFIG" -eq 0 ]]; then
    mkdir -p "$SCRIPT_DIR/.env.d"
    for env_name in "${ENV_FILES[@]}"; do
        cp "$SCRIPT_DIR/.env.example.d/$env_name" "$SCRIPT_DIR/.env.d/$env_name"
    done
    chmod 600 "$SCRIPT_DIR/.env.d/"*.env
    info "Created .env.d from .env.example.d."
    fail "Add BOT_TOKEN to .env.d/telegram.env, then run ./start.sh again."
fi


if ! CONFIG_SUMMARY="$("$PYTHON" - <<'PYCONFIG'
from core.proxy_config import load_proxy_settings
from core.settings import get_settings
from core.user_agent_config import load_user_agent_settings

settings = get_settings()
proxy_settings = load_proxy_settings()
user_agent_settings = load_user_agent_settings()
print(settings.logging.directory)
print("1" if settings.telegram.bot_token else "0")
print("1" if settings.sources.mal_client_id else "0")
print("1" if settings.sources.anidb_client else "0")
print(settings.sources.jikan_port)
print(sum(1 for name in proxy_settings.profiles if proxy_settings.active(name)))
print(sum(1 for name in user_agent_settings.profiles if user_agent_settings.preferred(name)))
PYCONFIG
)"; then
    fail "Configuration loading failed. Check .env.d, legacy .env, .proxies.d, and .user-agents.d for invalid settings."
fi
mapfile -t CONFIG_LINES <<<"$CONFIG_SUMMARY"

[[ "${CONFIG_LINES[1]:-0}" == "1" ]] || fail "BOT_TOKEN is empty in .env.d/telegram.env (or legacy .env)."

if [[ -z "$LOG_DIR" ]]; then
    LOG_DIR="${CONFIG_LINES[0]:-$SCRIPT_DIR/logs}"
fi
if [[ "$LOG_DIR" != /* ]]; then
    LOG_DIR="$SCRIPT_DIR/$LOG_DIR"
fi
export LOG_DIR
export JIKAN_PORT="${JIKAN_PORT:-${CONFIG_LINES[4]:-8091}}"
info "Proxy profiles with enabled entries: ${CONFIG_LINES[5]:-0}."
info "User-Agent profiles with custom entries: ${CONFIG_LINES[6]:-0}."

if [[ "${CONFIG_LINES[2]:-0}" != "1" ]]; then
    info "MAL_CLIENT_ID is empty: MyAnimeList search and metadata will be unavailable."
    info "Available non-MAL sources can still provide partial search and metadata results."
fi

if [[ "${CONFIG_LINES[3]:-0}" != "1" ]]; then
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
info "Default /anime search: Shikimori + MAL (MyAnimeList) / Jikan + AniList + Kitsu."
info "External IDs are enriched locally from disk-backed mappings.db."
info "Interactive /anime sources: All / MAL (MyAnimeList) / Jikan / Shikimori / AniList / Kitsu."
info "Direct external-ID lookup is source-independent."
info "Metadata sources: Shikimori + MAL (MyAnimeList) / Jikan + AniList + Kitsu + optional AniDB + AniSearch."
info "Staff/seiyuu/characters and episode backends are loaded lazily."
info "Use scripts/check.sh for compile/tests and scripts/update-mappings.sh for an explicit mapping refresh."

mkdir -p "$LOG_DIR"
CURRENT_LOG_DIR="$LOG_DIR/$(date '+%Y.%m.%d')"
BOT_LOG_FILE="$CURRENT_LOG_DIR/bot.log"
ERROR_LOG_FILE="$CURRENT_LOG_DIR/errors.log"

tmux new-session -d \
    -s "$SESSION_NAME" \
    -c "$SCRIPT_DIR" \
    "exec '$PYTHON' -m '$BOT_MODULE'"

sleep 1

if tmux has-session -t "$SESSION_NAME" 2>/dev/null; then
    info "Bot started in tmux session '$SESSION_NAME'."
    info "Module:  $BOT_MODULE"
    info "Attach:  tmux attach -t $SESSION_NAME"
    info "Logs:    $LOG_DIR/YYYY.MM.DD/{bot.log,users.log,api.log,errors.log}"
    info "Today:   tail -f '$BOT_LOG_FILE'"
else
    printf '\n' >&2
    if [[ -f "$ERROR_LOG_FILE" ]]; then
        tail -n 50 "$ERROR_LOG_FILE" >&2
    elif [[ -f "$BOT_LOG_FILE" ]]; then
        tail -n 50 "$BOT_LOG_FILE" >&2
    fi
    fail "The bot exited immediately. See $CURRENT_LOG_DIR for diagnostics."
fi
