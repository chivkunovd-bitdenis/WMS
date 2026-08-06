#!/usr/bin/env bash
set -euo pipefail

repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
project_name="${FBS_E2E_PROJECT_NAME:-wms-fbs-e2e-$(date +%s)-$$}"

if [[ "$project_name" == "wms-fbs-fullstack-e2e" ]]; then
  echo "Refusing to reuse the manual FBS project: $project_name" >&2
  exit 64
fi

seed_file="$(mktemp "${TMPDIR:-/tmp}/wms-fbs-e2e-seed.XXXXXX")"

read -r default_db_port default_redis_port default_api_port default_web_port \
  default_seller_web_port default_emulator_port < <(
  python3 - <<'PY'
import socket

sockets = []
for _ in range(6):
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    sockets.append(sock)
print(*(sock.getsockname()[1] for sock in sockets))
for sock in sockets:
    sock.close()
PY
)

export WMS_DB_PORT="${WMS_DB_PORT:-$default_db_port}"
export WMS_REDIS_PORT="${WMS_REDIS_PORT:-$default_redis_port}"
export WMS_API_PORT="${WMS_API_PORT:-$default_api_port}"
export WMS_WEB_PORT="${WMS_WEB_PORT:-$default_web_port}"
export WMS_SELLER_WEB_PORT="${WMS_SELLER_WEB_PORT:-$default_seller_web_port}"
export WB_EMULATOR_PORT="${WB_EMULATOR_PORT:-$default_emulator_port}"
export WB_EMULATOR_ADMIN_TOKEN="${WB_EMULATOR_ADMIN_TOKEN:-fbs-e2e-admin}"
export CONF_FBS_POLL_INTERVAL_SEC="${CONF_FBS_POLL_INTERVAL_SEC:-60}"
export CONF_FBS_STATUSES_SYNC_INTERVAL_SEC="${CONF_FBS_STATUSES_SYNC_INTERVAL_SEC:-120}"

compose=(docker compose -p "$project_name" -f "$repo_dir/docker-compose.yml" -f "$repo_dir/docker-compose.emulator.yml")

cleanup() {
  rm -f "$seed_file"
  if [[ "${KEEP_FBS_E2E_STACK:-0}" != "1" ]]; then
    "${compose[@]}" down -v --remove-orphans
  fi
}
trap cleanup EXIT

if [[ "${FBS_E2E_SKIP_BUILD:-0}" == "1" ]]; then
  "${compose[@]}" up -d db redis wb-emulator api
else
  "${compose[@]}" up -d --build db redis wb-emulator api
fi

for _ in {1..120}; do
  if curl --fail --silent "http://127.0.0.1:$WMS_API_PORT/health" >/dev/null; then
    break
  fi
  sleep 1
done
curl --fail --silent "http://127.0.0.1:$WMS_API_PORT/health" >/dev/null

# The API entrypoint runs Alembic. Start the worker only after the API is healthy
# so two fresh containers cannot race while creating alembic_version.
if [[ "${FBS_E2E_SKIP_BUILD:-0}" == "1" ]]; then
  "${compose[@]}" up -d celery_worker celery_beat web
else
  "${compose[@]}" up -d --build celery_worker celery_beat web
fi

for _ in {1..60}; do
  if curl --fail --silent "http://127.0.0.1:$WMS_WEB_PORT/" >/dev/null; then
    break
  fi
  sleep 1
done
curl --fail --silent "http://127.0.0.1:$WMS_WEB_PORT/" >/dev/null

for _ in {1..90}; do
  worker_ping="$(
    "${compose[@]}" exec -T celery_worker \
      celery -A app.celery_app inspect ping --timeout=2 2>&1 || true
  )"
  if rg -q "pong" <<<"$worker_ping"; then
    break
  fi
  sleep 1
done
worker_ping="$(
  "${compose[@]}" exec -T celery_worker \
    celery -A app.celery_app inspect ping --timeout=5 2>&1 || true
)"
rg -q "pong" <<<"$worker_ping"

running_services="$("${compose[@]}" ps --status running --services)"
rg -x -q "celery_beat" <<<"$running_services"

"${compose[@]}" exec -T \
  -e WB_EMULATOR_ADMIN_TOKEN="$WB_EMULATOR_ADMIN_TOKEN" \
  -e FBS_E2E_PUBLIC_EMULATOR_BASE="http://127.0.0.1:$WB_EMULATOR_PORT" \
  api python -m tests.fbs_browser_e2e_seed > "$seed_file"

(
  cd "$repo_dir/frontend"
  FBS_E2E_SEED_FILE="$seed_file" \
  FBS_E2E_EMULATOR_URL="http://127.0.0.1:$WB_EMULATOR_PORT" \
  WMS_WEB_PORT="$WMS_WEB_PORT" \
    npx playwright test -c playwright.fbs-fullstack.config.ts tests-e2e/ff-fbs-full-flow.spec.ts
)
