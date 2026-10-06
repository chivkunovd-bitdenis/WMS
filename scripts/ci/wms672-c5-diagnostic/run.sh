#!/usr/bin/env bash
set -euo pipefail
[[ "${GITHUB_ACTIONS:-}" == true && "$(uname -s)" == Linux ]]
root="$(pwd)"
evidence="${RUNNER_TEMP:?}/c5-peer-drain-comparison"
mkdir -p "$evidence"
export WMS672_EVIDENCE_DIR="$evidence/672"
export WMS672_TEST_URL=http://127.0.0.1:16724
protected=(frontend/tests-e2e/wms672-box-labels.test.mjs frontend/src/utils/printBarcodeLabel.ts frontend/src/screens/ff/FfInboundRequestView.tsx frontend/tests-e2e/wms672-native-errors.test.mjs frontend/tests-e2e/wms672-peer-drain.test.mjs)
for file in "${protected[@]}"; do git show "47817f76589701ea36ba1f8b30fca84b6a136208:$file" | cmp - "$file"; done
sha256sum "${protected[@]}" > "$evidence/source-before.sha256"
node --version > "$evidence/environment.txt"
uname -a >> "$evidence/environment.txt"
cat /etc/os-release >> "$evidence/environment.txt"
node --test --test-reporter=tap frontend/tests-e2e/wms672-peer-drain.test.mjs | tee "$evidence/672-peer-drain.tap"
node --test --test-reporter=tap frontend/tests-e2e/wms672-native-errors.test.mjs | tee "$evidence/672-native-errors.tap"
cd frontend
node node_modules/vite/bin/vite.js --config tests-e2e/wms672-c5-diagnostic.config.mjs --host 127.0.0.1 --port 16724 --strictPort > "$evidence/vite.log" 2>&1 &
vite_pid=$!
trap 'kill "$vite_pid" 2>/dev/null || true' EXIT
for attempt in {1..40}; do
  if curl --fail --silent "$WMS672_TEST_URL/tests-e2e/wms672-harness.html" >/dev/null; then break; fi
  sleep 1
done
curl --fail --silent "$WMS672_TEST_URL/tests-e2e/wms672-harness.html" >/dev/null
set +e
timeout 420s node --import ../scripts/ci/wms672-c5-diagnostic/adapter.mjs --test --test-reporter=tap --test-concurrency=1 --test-name-pattern='^C5 ' tests-e2e/wms672-box-labels.test.mjs 2>&1 | tee "$evidence/672-c5.tap"
result=${PIPESTATUS[0]}
set -e
cd "$root"
node scripts/ci/wms672-c5-diagnostic/analyze.mjs > "$evidence/analysis.txt"
sha256sum "${protected[@]}" > "$evidence/source-after.sha256"
cmp "$evidence/source-before.sha256" "$evidence/source-after.sha256"
exit "$result"
