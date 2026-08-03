#!/usr/bin/env bash
set -euo pipefail

# Isolated local WMS + WB emulator stack. It neither uses real WB credentials
# nor touches any running default compose project. Containers are deliberately
# left up after the test so the operator can inspect the same UI afterwards.
repo_root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$repo_root"

project_name="${FBS_LIVE_COMPOSE_PROJECT:-wms-fbs-live}"
web_port="${E2E_LIVE_WEB_PORT:-19173}"
api_port="${E2E_LIVE_API_PORT:-19080}"
emu_port="${E2E_LIVE_EMULATOR_PORT:-19081}"
run_id="$(date +%s)-$RANDOM"
wb_seller_key="fbs_live_${run_id}"
wb_token="fbs-live-${run_id}"
override_file="$(mktemp "${TMPDIR:-/tmp}/wms-fbs-live.XXXXXX.yml")"
trap 'rm -f "$override_file"' EXIT

printf '%s\n' 'services:' '  wb-emulator:' '    environment:' > "$override_file"
printf '      WB_EMULATOR_TOKEN_MAP: '\''{"%s":"%s"}'\''\n' "$wb_token" "$wb_seller_key" >> "$override_file"
printf '%s\n' '      WB_EMULATOR_ADMIN_TOKEN: "fbs-live-local-admin"' >> "$override_file"

export WMS_DB_PORT="${WMS_DB_PORT:-15433}"
export WMS_REDIS_PORT="${WMS_REDIS_PORT:-17379}"
export WMS_API_PORT="$api_port"
export WB_EMULATOR_PORT="$emu_port"

docker compose -p "$project_name" \
  -f docker-compose.yml -f docker-compose.emulator.yml -f "$override_file" \
  up -d --build db redis api wb-emulator

for _ in $(seq 1 60); do
  if curl -fsS "http://127.0.0.1:${api_port}/health" >/dev/null; then
    break
  fi
  sleep 1
done
curl -fsS "http://127.0.0.1:${api_port}/health" >/dev/null

# The API container owns the initial Alembic upgrade. Starting the worker only
# after its health endpoint is up avoids two containers racing to create the
# alembic_version table on a fresh isolated database.
docker compose -p "$project_name" \
  -f docker-compose.yml -f docker-compose.emulator.yml -f "$override_file" \
  up -d celery_worker celery_beat

# `up -d` only says containers started. The browser shell (Vite) is managed by
# Playwright; wait only for the real WMS API and the WB emulator here.
ready=0
for _attempt in $(seq 1 60); do
  if curl -fsS "http://127.0.0.1:${api_port}/health" >/dev/null \
    && curl -fsS "http://127.0.0.1:${emu_port}/health" >/dev/null; then
    ready=1
    break
  fi
  sleep 1
done
if [ "$ready" -ne 1 ]; then
  echo "Live FBS stack did not become ready within 60 seconds." >&2
  exit 1
fi

(
  cd frontend
  E2E_LIVE_WEB_URL="http://127.0.0.1:${web_port}" \
  E2E_LIVE_WEB_PORT="$web_port" \
  E2E_LIVE_API_URL="http://127.0.0.1:${api_port}" \
  E2E_LIVE_EMULATOR_URL="http://127.0.0.1:${emu_port}" \
  E2E_LIVE_EMULATOR_ADMIN_TOKEN='fbs-live-local-admin' \
  E2E_LIVE_WB_TOKEN="$wb_token" \
  E2E_LIVE_WB_SELLER_KEY="$wb_seller_key" \
  npx playwright test -c playwright.live-fbs.config.ts
)

printf '\nLive API and WB emulator are still running. To open the UI for manual testing:\n'
printf '  cd frontend && VITE_API_PROXY=http://127.0.0.1:%s npm run dev -- --host 127.0.0.1 --port %s\n' "$api_port" "$web_port"
printf '  then open http://127.0.0.1:%s\n' "$web_port"
printf 'Stop it: docker compose -p %s -f docker-compose.yml -f docker-compose.emulator.yml down -v\n' "$project_name"
