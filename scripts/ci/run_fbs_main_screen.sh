#!/usr/bin/env bash
# Builds an isolated real WMS stack; requires Docker and installed Playwright.
set -euo pipefail
cd "$(dirname "$0")/../.."
export FBS_MAIN_EVIDENCE="${FBS_MAIN_EVIDENCE:-$PWD/artifacts/fbs-main-screen}"
mkdir -p "$FBS_MAIN_EVIDENCE"
git rev-parse HEAD > "$FBS_MAIN_EVIDENCE/sha.txt"
# Unique project/ports prevent touching an operator's existing local containers.
export WMS_DB_PORT=25433 WMS_REDIS_PORT=26379 WMS_API_PORT=28080
export WB_EMULATOR_PORT=28081 WMS_WEB_PORT=25173
export FBS_MAIN_URL=http://127.0.0.1:25173
project="fbs-main-screen-$(date +%s)-$$"
printf '%s\n' "$project" > "$FBS_MAIN_EVIDENCE/compose-project.txt"
compose=(docker compose --project-name "$project" -f docker-compose.yml -f docker-compose.emulator.yml -f frontend/tests-e2e/fbs-main-screen/compose.yml)
cleanup() {
  if [[ -n "${mutation_backup:-}" ]]; then cp "$mutation_backup" "$mutation_source"; fi
  if [[ -n "${preview_pid:-}" ]]; then kill "$preview_pid" 2>/dev/null || true; fi
  "${compose[@]}" logs --no-color > "$FBS_MAIN_EVIDENCE/compose.log" 2>&1 || true
  "${compose[@]}" down --volumes --remove-orphans || true
}
trap cleanup EXIT
"${compose[@]}" up --detach --build --wait --wait-timeout 240 db redis migrations wb-emulator api celery_worker
npm ci --prefix frontend
npm run build --prefix frontend > "$FBS_MAIN_EVIDENCE/frontend-build.log" 2>&1
(cd frontend && VITE_API_PROXY=http://127.0.0.1:28080 node node_modules/vite/bin/vite.js preview --host 127.0.0.1 --port 25173 --strictPort) > "$FBS_MAIN_EVIDENCE/frontend-preview.log" 2>&1 &
preview_pid=$!
for attempt in {1..60}; do
  if curl --fail --silent "$FBS_MAIN_URL/app/ff/fbs" >/dev/null; then break; fi
  sleep 1
done
curl --fail --silent "$FBS_MAIN_URL/app/ff/fbs" >/dev/null
"${compose[@]}" exec -T -e FBS_MAIN_DISPOSABLE=1 api python -m tests.fbs_main_screen_seed > "$FBS_MAIN_EVIDENCE/seed.json"
export FBS_MAIN_SEED="$FBS_MAIN_EVIDENCE/seed.json"
mkdir -p "$FBS_MAIN_EVIDENCE/baseline"
# Baseline and mutant run before arrival/create/add, on the same unchanged DB.
if FBS_MAIN_EVIDENCE="$FBS_MAIN_EVIDENCE/baseline" FBS_MAIN_CASES=S1-six-tabs-and-exact-membership node frontend/tests-e2e/fbs-main-screen/browser.mjs > "$FBS_MAIN_EVIDENCE/baseline/browser.log" 2>&1; then
  mutation_source="$PWD/frontend/src/screens/v2/FfFbsOrdersScreen.tsx"
  mutation_backup="$FBS_MAIN_EVIDENCE/original-FfFbsOrdersScreen.tsx"
  cp "$mutation_source" "$mutation_backup"
  python3 -c 'from pathlib import Path; import sys; p=Path(sys.argv[1]); s=p.read_text(); old="setOrders(page.items)"; assert s.count(old)==1; p.write_text(s.replace(old,"setOrders([])"))' "$mutation_source"
  mkdir -p "$FBS_MAIN_EVIDENCE/mutation"
  sha256sum "$mutation_source" > "$FBS_MAIN_EVIDENCE/mutation/source.sha256"
  (cd frontend && node node_modules/vite/bin/vite.js build) > "$FBS_MAIN_EVIDENCE/mutation/build.log" 2>&1
  mutation_status=0
  FBS_MAIN_EVIDENCE="$FBS_MAIN_EVIDENCE/mutation" FBS_MAIN_CASES=S1-six-tabs-and-exact-membership node frontend/tests-e2e/fbs-main-screen/browser.mjs > "$FBS_MAIN_EVIDENCE/mutation/browser.log" 2>&1 || mutation_status=$?
  cp "$mutation_backup" "$mutation_source"
  mutation_backup=""
  node -e 'const fs=require("fs"); const r=JSON.parse(fs.readFileSync(process.argv[1])); const c=r[0]; const proved=r.length===1&&c.status==="failed"&&c.phase==="setup"&&c.expectedOrderIds.length>0&&Array.isArray(c.actualOrderIds)&&c.actualOrderIds.length===0&&c.browserErrors.length===0&&c.worklistSnapshots.some(s=>s.status===200&&s.ids.length>0)&&process.argv[3]==="1"; fs.writeFileSync(process.argv[2], JSON.stringify({proved, mutation:"setOrders(page.items) -> setOrders([])", baseline:"S1 passed", observed:c},null,2)); if(!proved)process.exit(1)' "$FBS_MAIN_EVIDENCE/mutation/results.json" "$FBS_MAIN_EVIDENCE/mutation/proof.json" "$mutation_status"
  (cd frontend && node node_modules/vite/bin/vite.js build) > "$FBS_MAIN_EVIDENCE/restored-build.log" 2>&1
fi
browser_status=0
node frontend/tests-e2e/fbs-main-screen/browser.mjs || browser_status=$?
"${compose[@]}" exec -T -e FBS_MAIN_DISPOSABLE=1 api python -m tests.fbs_main_screen_verify < "$FBS_MAIN_SEED" > "$FBS_MAIN_EVIDENCE/physical-stock.json"
exit "$browser_status"
