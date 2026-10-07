#!/usr/bin/env bash
# Diagnostic branch only: frozen real QR body plus separate transport measurement.
set -euo pipefail
[[ "${GITHUB_ACTIONS:-}" == true && "$(uname -s)" == Linux && "$(node --version)" == v24.21.0 ]]
export WMS652_CHROME="${WMS672_CHROMIUM:?}"
evidence="${RUNNER_TEMP:?}/wms652-realqr-lifecycle"
mkdir -p "$evidence"
export WMS652_EVIDENCE="$evidence/selected"
export WMS652_DIAGNOSTIC_PROVENANCE="$evidence/provenance.json"
mkdir -p "$WMS652_EVIDENCE"
# Historical Actions merge is not guaranteed to be reachable from branch history.
git fetch --no-tags origin ac845328b27b5be265962695e10766efddef339e
protected=(frontend/tests-e2e/wms652-critical/browser.mjs frontend/tests-e2e/wms652-critical/fixtures.mjs frontend/tests-e2e/wms652-critical/geometry.mjs frontend/tests-e2e/wms652-critical/cases.json frontend/tests-e2e/wms652-critical/main.tsx frontend/tests-e2e/wms652-critical/index.html frontend/tests-e2e/wms652-critical/vite.config.ts frontend/package.json frontend/package-lock.json)
for file in "${protected[@]}"; do git show "7bbfafc68ef0834746e63f12a49db31a1977f030:$file" | cmp - "$file"; done
sha256sum "${protected[@]}" > "$evidence/protected-before.sha256"
node --version > "$evidence/environment.txt"
uname -a >> "$evidence/environment.txt"
cat /etc/os-release >> "$evidence/environment.txt"
"$WMS652_CHROME" --version >> "$evidence/environment.txt"
node scripts/ci/wms652-realqr-diagnostic/prepare.mjs > "$evidence/preparation.log"
cp frontend/tests-e2e/wms652-critical/.lifecycle-diagnostic.untracked.mjs "$evidence/selected-runner.mjs"
cp frontend/tests-e2e/wms652-critical/.lifecycle-transport-observer.untracked.mjs "$evidence/transport-observer.mjs"
node frontend/node_modules/vite/bin/vite.js --config frontend/tests-e2e/wms652-critical/vite.config.ts > "$evidence/vite.log" 2>&1 &
vite_pid=$!
trap 'kill "$vite_pid" 2>/dev/null || true' EXIT
for attempt in {1..40}; do
  if curl --fail --silent http://127.0.0.1:16686/app/ff/fbs >/dev/null; then break; fi
  sleep 1
done
curl --fail --silent http://127.0.0.1:16686/app/ff/fbs >/dev/null
set +e
timeout 600s node frontend/tests-e2e/wms652-critical/.lifecycle-diagnostic.untracked.mjs > "$evidence/selected.log" 2>&1
selected_result=$?
export WMS652_EVIDENCE="$evidence/transport"
mkdir -p "$WMS652_EVIDENCE"
timeout 60s node scripts/ci/wms652-realqr-diagnostic/transport-probe.mjs > "$evidence/transport.log" 2>&1
transport_result=$?
set -e
sha256sum "${protected[@]}" > "$evidence/protected-after.sha256"
cmp "$evidence/protected-before.sha256" "$evidence/protected-after.sha256"
printf '{"selected_exit":%s,"transport_exit":%s}\n' "$selected_result" "$transport_result" > "$evidence/exit-results.json"
if (( selected_result != 0 )); then exit "$selected_result"; fi
exit "$transport_result"
