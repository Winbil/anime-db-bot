#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_DIR="${PROJECT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
CONTAINER_NAME="${JIKAN_CONTAINER_NAME:-anime-db-bot-Jikan}"
SERVICE_NAME="jikan"
CURRENT_IMAGE="anime-db-bot-jikan:current"
CANDIDATE_IMAGE="anime-db-bot-jikan:candidate"
ROLLBACK_IMAGE="anime-db-bot-jikan:rollback"
PORT="${JIKAN_PORT:-8091}"
API="http://127.0.0.1:${PORT}"
MAX_IDLE_WAIT_SECONDS="${JIKAN_UPDATE_IDLE_WAIT_SECONDS:-300}"
MAX_SWITCH_ATTEMPTS=3

log() { printf '[jikan-updater] %s\n' "$*"; }

cd "$PROJECT_DIR"

latest_tag="$({ curl -fsSL --connect-timeout 10 --max-time 30 \
  -H 'Accept: application/vnd.github+json' \
  https://api.github.com/repos/jikan-me/jikan/releases/latest || true; } \
  | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("tag_name", ""))' 2>/dev/null || true)"
latest_version="${latest_tag#v}"
if [[ -z "$latest_version" ]]; then
  log 'Could not determine latest Jikan release; keeping current container.'
  exit 0
fi

current_version="$(curl -fsS --connect-timeout 3 --max-time 5 "$API/version" \
  | python3 -c 'import json,sys; print(json.load(sys.stdin).get("jikan_version", ""))' 2>/dev/null || true)"
current_version="${current_version#v}"
if [[ "$current_version" == "$latest_version" ]]; then
  log "Jikan is current ($current_version)."
  exit 0
fi

if ! docker inspect "$CONTAINER_NAME" >/dev/null 2>&1; then
  log "Container $CONTAINER_NAME is missing; building current Jikan release $latest_version."
  docker compose build --pull "$SERVICE_NAME"
  docker compose up -d --no-build "$SERVICE_NAME"
  exit 0
fi

old_image_id="$(docker inspect --format '{{.Image}}' "$CONTAINER_NAME")"

wait_until_idle() {
  local waited=0
  while docker exec "$CONTAINER_NAME" test -e /tmp/anime-db-bot-jikan-active.lock >/dev/null 2>&1; do
    if (( waited >= MAX_IDLE_WAIT_SECONDS )); then
      return 1
    fi
    sleep 2
    waited=$((waited + 2))
  done
}

if ! wait_until_idle; then
  log 'Jikan is still in active use; deferring update until the next daily check.'
  exit 0
fi

docker tag "$old_image_id" "$ROLLBACK_IMAGE"

rollback() {
  log 'Restoring previous Jikan image.'
  docker compose rm -sf "$SERVICE_NAME" >/dev/null 2>&1 || true
  docker image rm -f "$CURRENT_IMAGE" >/dev/null 2>&1 || true
  docker tag "$ROLLBACK_IMAGE" "$CURRENT_IMAGE"
  docker compose up -d --no-build "$SERVICE_NAME"
}

for attempt in $(seq 1 "$MAX_SWITCH_ATTEMPTS"); do
  log "Updating Jikan $current_version -> $latest_version (attempt $attempt/$MAX_SWITCH_ATTEMPTS)."
  if docker inspect "$CONTAINER_NAME" >/dev/null 2>&1 && ! wait_until_idle; then
    log 'Jikan became busy again; deferring update.'
    exit 0
  fi

  docker compose stop "$SERVICE_NAME" >/dev/null 2>&1 || true
  docker compose rm -f "$SERVICE_NAME" >/dev/null 2>&1 || true
  docker image rm -f "$CANDIDATE_IMAGE" >/dev/null 2>&1 || true

  if docker build --pull --no-cache -f jikan_service/Dockerfile -t "$CANDIDATE_IMAGE" .; then
    docker tag "$CANDIDATE_IMAGE" "$CURRENT_IMAGE"
    if docker compose up -d --no-build "$SERVICE_NAME"; then
      healthy=0
      for _ in $(seq 1 30); do
        status="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$CONTAINER_NAME" 2>/dev/null || true)"
        if [[ "$status" == 'healthy' ]]; then
          healthy=1
          break
        fi
        sleep 2
      done
      running_version="$(curl -fsS --connect-timeout 3 --max-time 5 "$API/version" \
        | python3 -c 'import json,sys; print(json.load(sys.stdin).get("jikan_version", ""))' 2>/dev/null || true)"
      running_version="${running_version#v}"
      if [[ "$healthy" == 1 && "$running_version" == "$latest_version" ]]; then
        log "Jikan $latest_version started successfully."
        docker image rm -f "$ROLLBACK_IMAGE" >/dev/null 2>&1 || true
        if [[ "$old_image_id" != "$(docker inspect --format '{{.Image}}' "$CONTAINER_NAME")" ]]; then
          docker image rm -f "$old_image_id" >/dev/null 2>&1 || true
        fi
        docker image rm -f "$CANDIDATE_IMAGE" >/dev/null 2>&1 || true
        exit 0
      fi
      log "Candidate started incorrectly (health=$status, version=$running_version)."
    fi
  fi

  docker compose rm -sf "$SERVICE_NAME" >/dev/null 2>&1 || true
  sleep 2
done

rollback
log 'Update failed after three attempts; previous image restored. Will retry on the next daily check.'
exit 0
