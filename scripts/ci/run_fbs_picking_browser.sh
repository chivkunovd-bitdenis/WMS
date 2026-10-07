#!/usr/bin/env bash
# Builds an isolated real WMS stack; requires Docker and installed Playwright.
set -euo pipefail
cd "$(dirname "$0")/../.."
export FBS_PICK_EVIDENCE="${FBS_PICK_EVIDENCE:-$PWD/artifacts/fbs-picking}"
mkdir -p "$FBS_PICK_EVIDENCE"
git rev-parse HEAD > "$FBS_PICK_EVIDENCE/sha.txt"
# Unique project/ports prevent touching an operator's existing local containers.
export WMS_DB_PORT=25434 WMS_REDIS_PORT=26380 WMS_API_PORT=28082
export WB_EMULATOR_PORT=28083 WMS_WEB_PORT=25174
export FBS_PICK_URL=http://127.0.0.1:25174
project="fbs-picking-$(date +%s)-$$"
printf '%s\n' "$project" > "$FBS_PICK_EVIDENCE/compose-project.txt"
compose=(docker compose --project-name "$project" -f docker-compose.yml -f docker-compose.emulator.yml -f frontend/tests-e2e/fbs-picking/compose.yml)
cleanup() {
  if [[ -n "${preview_pid:-}" ]]; then kill "$preview_pid" 2>/dev/null || true; fi
  if [[ ! -f "$FBS_PICK_EVIDENCE/results.json" && ! -f "$FBS_PICK_EVIDENCE/status.json" ]]; then
    printf '{"status":"preparefailure","phase":"stack-build-or-browser-start"}\n' > "$FBS_PICK_EVIDENCE/status.json"
  fi
  "${compose[@]}" logs --no-color > "$FBS_PICK_EVIDENCE/compose.log" 2>&1 || true
  "${compose[@]}" down --volumes --remove-orphans || true
}
trap cleanup EXIT
"${compose[@]}" up --detach --build --wait --wait-timeout 240 db redis migrations wb-emulator api celery_worker
npm ci --prefix frontend
npm run build --prefix frontend > "$FBS_PICK_EVIDENCE/frontend-build.log" 2>&1
(cd frontend && VITE_API_PROXY=http://127.0.0.1:28082 node node_modules/vite/bin/vite.js preview --host 127.0.0.1 --port 25174 --strictPort) > "$FBS_PICK_EVIDENCE/frontend-preview.log" 2>&1 &
preview_pid=$!
for attempt in {1..60}; do
  if curl --fail --silent "$FBS_PICK_URL/app/ff/fbs" >/dev/null; then break; fi
  sleep 1
done
curl --fail --silent "$FBS_PICK_URL/app/ff/fbs" >/dev/null
if ! "${compose[@]}" exec -T -e FBS_PICK_DISPOSABLE=1 api python -m tests.fbs_picking_browser_seed > "$FBS_PICK_EVIDENCE/seed.json" 2> "$FBS_PICK_EVIDENCE/seed.log"; then
  printf '{"status":"preparefailure","phase":"seed"}\n' > "$FBS_PICK_EVIDENCE/status.json"
  exit 2
fi
export FBS_PICK_SEED="$FBS_PICK_EVIDENCE/seed.json"
export FBS_PICK_PROJECT="$project"
export FBS_PICK_CASES="${FBS_PICK_CASES:-}"
browser_status=0
node frontend/tests-e2e/fbs-picking/browser.mjs || browser_status=$?
"${compose[@]}" exec -T -e FBS_PICK_DISPOSABLE=1 api python -m tests.fbs_picking_browser_verify < "$FBS_PICK_SEED" > "$FBS_PICK_EVIDENCE/final-db.json"
node -e 'const fs=require("fs"); const r=JSON.parse(fs.readFileSync(process.argv[1],"utf8")); if(!r.unchanged || r.balances.some(b=>b.quantity<0))process.exit(1)' "$FBS_PICK_EVIDENCE/final-db.json"
exit "$browser_status"
