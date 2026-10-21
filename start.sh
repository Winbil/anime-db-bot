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

required_files=(
    "requirements.txt"
    "bots/common.py"
    "bots/people_portraits.py"
    "bots/runner.py"
    "bots/search_ui.py"
    "bots/official.py"
    "bots/tgapi.py"
    "core/models.py"
    "core/contracts.py"
    "core/canonicalization.py"
    "core/http_config.py"
    "services/search.py"
    "services/aggregator.py"
    "services/id_resolver.py"
    "search/registry.py"
    "search/providers/mal.py"
    "search/providers/shikimori.py"
    "search/providers/anilist.py"
    "sources/registry.py"
    "sources/shikimori.py"
    "sources/shikimori_people.py"
    "sources/anilist.py"
    "sources/mal.py"
    "tests/test_search.py"
    "tests/test_aggregator.py"
    "tests/test_shikimori_people.py"
    "tests/test_anilist_lazy.py"
)
for required_file in "${required_files[@]}"; do
    [[ -f "$SCRIPT_DIR/$required_file" ]] || fail "$required_file not found."
done

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

info "Compiling Python sources..."
"$PYTHON" -m compileall -q bots core search services sources tests

info "Running regression tests..."
"$PYTHON" -m unittest discover -s tests -v

info "Checking required imports and service wiring..."
"$PYTHON" - <<'PY'
import aiogram
import httpx
import dotenv
from aiogram.types import InputRichMessage
from bots import common as common_bot
from bots.people_portraits import _sources_with_portraits, handle_people_callback
from bots.runner import _CallbackRoutingMiddleware
from bots.search_ui import register_search_handlers
from core.canonicalization import (
    canonical_genre,
    canonical_role,
    is_primary_voice_role,
    person_identity_keys,
)
from core.contracts import AnimeSearchProvider, AnimeSource
from core.http_config import USER_AGENT
from core.models import AggregatedAnime, AnimeRecord, PersonCredit, SearchCandidate, SearchPage
from search.providers.anilist import AniListSearchProvider
from search.providers.mal import MALSearchProvider
from search.providers.shikimori import ShikimoriSearchProvider
from search.registry import get_search_provider_map, get_search_providers
from services.aggregator import AnimeAggregator, _merge_people
from services.search import SearchService
from sources.anilist import AniListSource
from sources.mal import MALSource
from sources.registry import get_sources
from sources.shikimori import ShikimoriSource
from sources.shikimori_people import _rest_voice_credits

providers = get_search_providers()
all_provider_map = get_search_provider_map()
sources = get_sources()
if not providers:
    raise RuntimeError("No default anime search providers are enabled in search/registry.py")
if not all_provider_map:
    raise RuntimeError("No selectable anime search providers are enabled")
if not sources:
    raise RuntimeError("No anime metadata sources are enabled in sources/registry.py")
if not USER_AGENT.startswith("anime-db-bot/"):
    raise RuntimeError("Shared HTTP User-Agent smoke test failed")
if not callable(handle_people_callback):
    raise RuntimeError("People callback routing smoke test failed")
_CallbackRoutingMiddleware()

if canonical_genre("Fantasy") != canonical_genre("Фэнтези"):
    raise RuntimeError("Genre canonicalization smoke test failed")
if canonical_role("Director") != canonical_role("Режиссёр"):
    raise RuntimeError("Role canonicalization smoke test failed")
if not (person_identity_keys(["Fuse"]) & person_identity_keys(["Фусэ", "Fuse"])):
    raise RuntimeError("Person alias canonicalization smoke test failed")
if not is_primary_voice_role("Сэйю"):
    raise RuntimeError("Primary seiyuu role smoke test failed")
if is_primary_voice_role("Сэйю (EN)"):
    raise RuntimeError("Foreign dub seiyuu filter smoke test failed")
if common_bot.SOURCE_SELECTABLE_SECTIONS != {"titles", "staff", "voices"}:
    raise RuntimeError("Source-selectable section registry smoke test failed")

shikimori_voice_smoke = _rest_voice_credits([{
    "roles": ["Main"],
    "roles_russian": ["Главная роль"],
    "person": {
        "id": 1,
        "name": "Test Seiyuu",
        "russian": "",
        "image": {},
    },
    "character": {
        "id": 2,
        "name": "Test Character",
        "russian": "Тестовый персонаж",
        "image": {},
    },
}])
if len(shikimori_voice_smoke) != 1:
    raise RuntimeError("Shikimori structural seiyuu link smoke test failed")
if shikimori_voice_smoke[0].roles != ["Озвучка: Тестовый персонаж"]:
    raise RuntimeError("Shikimori seiyuu character role smoke test failed")

portrait_merge = _merge_people([
    [PersonCredit(
        name="Test Person",
        portraits={"AniList": ["https://example.invalid/anilist.jpg"]},
    )],
    [PersonCredit(
        name="Test Person",
        portraits={"Shikimori": ["https://example.invalid/shikimori.jpg"]},
    )],
])
if len(portrait_merge) != 1 or set(portrait_merge[0].portraits) != {"AniList", "Shikimori"}:
    raise RuntimeError("Cross-source portrait merge smoke test failed")

sample = AggregatedAnime(
    title="Smoke test",
    sources=["AniList"],
    titles_by_source={"AniList": {"english": "Smoke test"}},
    staff=[PersonCredit(
        name="Test Person",
        portraits={"AniList": ["https://example.invalid/staff.jpg"]},
    )],
    voices=[PersonCredit(
        name="Test Voice",
        portraits={"AniList": ["https://example.invalid/voice.jpg"]},
    )],
    staff_by_source={"AniList": [PersonCredit(
        name="Test Person",
        portraits={"AniList": ["https://example.invalid/staff.jpg"]},
    )]},
    voices_by_source={"AniList": [PersonCredit(
        name="Test Voice",
        portraits={"AniList": ["https://example.invalid/voice.jpg"]},
    )]},
)
if common_bot._source_section_sources(sample, "titles") != ["AniList"]:
    raise RuntimeError("Title source provenance smoke test failed")
for section in ("staff", "voices"):
    if _sources_with_portraits(sample, section) != ["AniList"]:
        raise RuntimeError(f"Portrait source provenance smoke test failed for {section}")

SearchService(providers)
AnimeAggregator(sources)
print("Python imports and service wiring: OK")
print("Multilingual canonicalization: OK")
print("Original seiyuu filtering: OK")
print("Shikimori structural seiyuu links: OK")
print("Source-selectable metadata sections: OK")
print("Cross-source person portraits: OK")
print("Portrait callback routing: OK")
print("Default search providers:", ", ".join(provider.name for provider in providers))
print("Selectable search providers:", ", ".join(all_provider_map))
print("Metadata sources:", ", ".join(source.name for source in sources))
PY

if [[ ! -f "$SCRIPT_DIR/.env" ]]; then
    [[ -f "$SCRIPT_DIR/.env.example" ]] || fail ".env and .env.example are both missing."
    cp "$SCRIPT_DIR/.env.example" "$SCRIPT_DIR/.env"
    info "Created .env from .env.example."
    fail "Add BOT_TOKEN to .env, then run ./start.sh again."
fi

BOT_TOKEN_VALUE="$(sed -n 's/^[[:space:]]*BOT_TOKEN[[:space:]]*=[[:space:]]*//p' "$SCRIPT_DIR/.env" | tail -n 1 | tr -d '\r')"
[[ -n "$BOT_TOKEN_VALUE" ]] || fail "BOT_TOKEN is empty in .env."

MAL_CLIENT_ID_VALUE="$(sed -n 's/^[[:space:]]*MAL_CLIENT_ID[[:space:]]*=[[:space:]]*//p' "$SCRIPT_DIR/.env" | tail -n 1 | tr -d '\r')"
if [[ -z "$MAL_CLIENT_ID_VALUE" ]]; then
    info "MAL_CLIENT_ID is empty: MyAnimeList search and metadata will be unavailable."
    info "Shikimori search plus Shikimori/AniList metadata can still work."
    info "Optional MAL setup: https://myanimelist.net/apiconfig"
fi

TG_API_URL_VALUE="$(sed -n 's/^[[:space:]]*TELEGRAM_BOT_API_URL[[:space:]]*=[[:space:]]*//p' "$SCRIPT_DIR/.env" | tail -n 1 | tr -d '\r')"

if [[ -n "$TG_API_URL_VALUE" ]]; then
    BOT_MODULE="bots.tgapi"
    info "Selected Telegram transport: custom tg-bot-api."
else
    BOT_MODULE="bots.official"
    info "Selected Telegram transport: official api.telegram.org."
fi

info "Default search: Shikimori + MyAnimeList, merged by MAL ID."
info "Selectable /search providers include MAL, Shikimori and AniList."
info "Metadata sources: Shikimori + AniList + MyAnimeList."
info "Equivalent metadata fields are multilingual-canonicalized and merged without duplicates."
info "People data is loaded lazily when staff/seiyuu sections are opened."
info "Titles, staff and seiyuu keep source provenance for inline source switching."
info "Staff and seiyuu portraits are source-keyed and paginated one person per rich page."
info "Anime cards use sendRichMessage (up to 32768 UTF-8 chars) in both modes."

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
