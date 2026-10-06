#!/usr/bin/env bash
# Browser and PDF evidence; intercept printer transfer and forbid real marketplace I/O.
set -euo pipefail
[[ "${GITHUB_ACTIONS:-}" == true && "$(uname -s)" == Linux ]]
cd "$(dirname "$0")/../../frontend"
evidence="${RUNNER_TEMP:?}/release-print"
mkdir -p "$evidence"
export WMS672_TEST_URL=http://127.0.0.1:16724
export WMS672_EVIDENCE_DIR="$evidence/672"
export WMS673_RENDERED_ARTIFACTS_DIR="$evidence/673"
node node_modules/vite/bin/vite.js --config tests-e2e/wms672-vite.config.ts \
  --host 127.0.0.1 --port 16724 --strictPort > "$evidence/vite.log" 2>&1 &
vite_pid=$!
trap 'kill "$vite_pid" 2>/dev/null || true' EXIT
for attempt in {1..40}; do
  if curl --fail --silent "$WMS672_TEST_URL/tests-e2e/wms672-harness.html" >/dev/null; then break; fi
  sleep 1
done
curl --fail --silent "$WMS672_TEST_URL/tests-e2e/wms672-harness.html" >/dev/null
timeout 420s node --import ../scripts/ci/wms-print-contract-probe.mjs \
  --test --test-reporter=tap --test-concurrency=1 tests-e2e/wms672-box-labels.test.mjs | tee "$evidence/672.tap"
timeout 240s node --test --test-reporter=tap --test-concurrency=1 \
  tests-e2e/wms672-remaining.test.mjs | tee "$evidence/672-remaining.tap"
timeout 120s node ../scripts/ci/wms-print-contract-probe.mjs --render673
node node_modules/vitest/vitest.mjs run src/screens/v2/fbsPickingColor.wms673.pdf.test.ts \
  --maxWorkers=1 --no-file-parallelism --reporter=json --outputFile="$evidence/673.json"
python - "$evidence" <<'PY'
import json, pathlib, re, sys
root = pathlib.Path(sys.argv[1])
for name, expected in [('672.tap', 11), ('672-remaining.tap', 6)]:
    text = (root / name).read_text()
    for key, value in [('tests', expected), ('pass', expected), ('fail', 0), ('cancelled', 0), ('skipped', 0), ('todo', 0)]:
        matches = re.findall(r'^# ' + key + r' (\d+)$', text, re.M)
        assert matches == [str(value)], (name, key, matches, value)
    print(f'{name}: {expected} executed, no skipped/failure/cancelled')
for name, expected in [('673.json', 5)]:
    data = json.loads((root / name).read_text())
    assert data['success'] and data['numTotalTests'] == expected, (name, data)
    assert data['numPassedTests'] == expected and data['numPendingTests'] == 0, (name, data)
    assert data['numFailedTests'] == 0, (name, data)
    print(f'{name}: {expected} executed, no skipped/failure')
PY
