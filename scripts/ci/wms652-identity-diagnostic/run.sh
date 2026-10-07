#!/usr/bin/env bash
# Diagnostic branch only: one unchanged 43-case browser command, no other suites.
set -euo pipefail
cd "$(dirname "$0")/../../.."
out="${RUNNER_TEMP:?}/wms652-identity-diagnostic"
mkdir -p "$out"
export WMS652_EVIDENCE="$RUNNER_TEMP/release-print/critical-fbs"
mkdir -p "$WMS652_EVIDENCE"
node --test --test-reporter=tap scripts/ci/wms652-identity-diagnostic/observer.test.mjs > "$out/observer-controls.tap"
node --test --test-reporter=tap scripts/ci/wms652-identity-diagnostic/error-context.test.mjs > "$out/error-context-controls.tap"
node --test --test-reporter=tap scripts/ci/wms652-identity-diagnostic/job-lookup.test.mjs > "$out/job-lookup-controls.tap"
python3 scripts/ci/wms652-identity-diagnostic/prepare.py "$out" > "$out/preparation-summary.json"
node --check frontend/tests-e2e/wms652-critical/browser.identity-diagnostic.untracked.mjs
node --check frontend/tests-e2e/wms652-critical/identity-observer.untracked.mjs
node --check frontend/tests-e2e/wms652-critical/error-context.mjs
bash -n scripts/ci/run_critical_fbs_browser.observed.untracked.sh
{
  uname -a
  cat /etc/os-release
  node --version
  "$WMS672_CHROMIUM" --version
  node -p "require(process.env.RUNNER_TEMP+'/print-contract-tools/node_modules/playwright/package.json').version"
  git rev-parse HEAD
} > "$out/environment.txt"
"$WMS672_CHROMIUM" --version | grep -Eq '141\.'
set +e
bash scripts/ci/run_critical_fbs_browser.observed.untracked.sh > "$out/browser43.log" 2>&1
browser_exit=$?
set -e
python3 - "$out" "$browser_exit" <<'PY'
import hashlib, json, os, sys
from pathlib import Path
out=Path(sys.argv[1]); code=int(sys.argv[2]); raw=Path(os.environ['WMS652_EVIDENCE'])
result=raw/'result.json'
report=json.loads(result.read_text()) if result.exists() else None
expected=json.loads(Path('frontend/tests-e2e/wms652-critical/cases.json').read_text())
complete=bool(report and [x['id'] for x in report['cases']]==expected)
strict_pass=bool(complete and report.get('status')=='PASS' and all(x['status']=='PASS' for x in report['cases']))
after={p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in json.loads((out/'preparation.json').read_text())['source_sha256']}
unchanged=after==json.loads((out/'preparation.json').read_text())['source_sha256']
(out/'source-after.json').write_text(json.dumps(after,indent=2)+'\n')
(out/'exit-results.json').write_text(json.dumps({'original_browser_command_exit':code,'exact43_complete':complete,'strict43_pass':strict_pass,'source_bytes_unchanged':unchanged,'actual_run':True},indent=2)+'\n')
if not complete or not strict_pass or not unchanged: sys.exit(1)
PY
exit "$browser_exit"
