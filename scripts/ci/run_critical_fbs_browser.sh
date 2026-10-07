#!/usr/bin/env bash
# Existing application screens, synthetic API/native-printer boundaries only.
set -euo pipefail
cd "$(dirname "$0")/../.."
export WMS652_CHROME="${WMS672_CHROMIUM:?Chromium must be installed}"
export WMS652_EVIDENCE="${RUNNER_TEMP:?}/release-print/critical-fbs"
mkdir -p "$WMS652_EVIDENCE"
node frontend/node_modules/vite/bin/vite.js --config frontend/tests-e2e/wms652-critical/vite.config.ts \
  > "$WMS652_EVIDENCE/vite.log" 2>&1 &
vite_pid=$!
trap 'kill "$vite_pid" 2>/dev/null || true' EXIT
for attempt in {1..40}; do
  if curl --fail --silent http://127.0.0.1:16686/app/ff/fbs >/dev/null; then break; fi
  sleep 1
done
curl --fail --silent http://127.0.0.1:16686/app/ff/fbs >/dev/null
status=0
timeout 600s node frontend/tests-e2e/wms652-critical/browser.mjs || status=$?
if [ "$status" = 0 ]; then exit 0; fi
# Reinitialize the synthetic browser once only after every business assertion
# passed and the final audit found solely the known native interception failure.
# Keep the original full failure; never retry a CDP command or a business defect.
python3 - "$WMS652_EVIDENCE" <<'RECOVERY'
import json, pathlib, re, subprocess, sys

def eligible(report, expected, snapshots, transport):
    if report.get('status') != 'FAIL' or report.get('failure') != 'AssertionError [ERR_ASSERTION]: one or more real-screen cases failed':
        return False
    cases = report.get('cases', [])
    if [c.get('id') for c in cases] != expected or any(c.get('status') not in {'PASS', 'FAIL'} for c in cases):
        return False
    failed = [c for c in cases if c['status'] == 'FAIL']
    if not failed or transport.get('pendingCommandIds') != []:
        return False
    signature = {'code': -32602, 'message': 'Invalid InterceptionId.'}
    for case in failed:
        if not case['id'].startswith('WMS652.realQrFlags[') or case.get('businessAssertionsPassed') is not True:
            return False
        data = snapshots.get(case['id'], {})
        if data.get('blocked') != [] or not data.get('errors'):
            return False
        for error in data['errors']:
            if not isinstance(error, str) or not error.startswith('Error: '):
                return False
            try:
                if json.loads(error[7:]) != signature: return False
            except ValueError:
                return False
        native = [e for e in transport.get('events', []) if e.get('kind') == 'command-result'
                  and e.get('caseId') == case['id'] and e.get('method') == 'Fetch.fulfillRequest'
                  and e.get('nativeError') == signature]
        if len(native) != len(data['errors']): return False
    return True

root = pathlib.Path(sys.argv[1])
report = json.loads((root / 'result.json').read_text())
expected = json.loads(pathlib.Path('frontend/tests-e2e/wms652-critical/cases.json').read_text())
transport = json.loads((root / 'cdp-transport.json').read_text())
snapshots = {c['id']: json.loads((root / (re.sub('[^a-zA-Z0-9_-]', '-', c['id']) + '.json')).read_text())
             for c in report['cases'] if c['status'] == 'FAIL'}
if report.get('sha') != subprocess.check_output(['git','rev-parse','HEAD'], text=True).strip() or not eligible(report, expected, snapshots, transport):
    sys.exit('Strict browser failure retained; not eligible for bounded transport reinitialization')
(root / 'transport-recovery-decision.json').write_text(json.dumps(dict(
    action='one-fresh-synthetic-browser-process', first_status='FAIL',
    failed_cases=[c['id'] for c in report['cases'] if c['status']=='FAIL'],
    native_error={'code':-32602,'message':'Invalid InterceptionId.'},
    business_assertions_passed=True, maximum_process_attempts=2,
    native_command_retries=0), indent=2)+'\n')
RECOVERY
# The native process must be gone before starting its replacement on the same
# fixture port. Browser runner already closes its own WebSocket and Chrome.
test ! -e "${WMS652_EVIDENCE}-transport-attempt-1"
mv "$WMS652_EVIDENCE" "${WMS652_EVIDENCE}-transport-attempt-1"
mkdir -p "$WMS652_EVIDENCE"
echo 'Preserved first transport-only FAIL; executing every strict case in one fresh synthetic browser'
timeout 600s node frontend/tests-e2e/wms652-critical/browser.mjs
