#!/usr/bin/env bash
set -euo pipefail
[[ "${GITHUB_ACTIONS:-}" == true && "$(uname -s)" == Linux && "$(node --version)" == v24.21.0 ]]
export WMS652_CHROME="${WMS672_CHROMIUM:?}"
export WMS652_EVIDENCE="${RUNNER_TEMP:?}/wms652-explicit-abort"
mkdir -p "$WMS652_EVIDENCE"
node --version > "$WMS652_EVIDENCE/environment.txt"
uname -a >> "$WMS652_EVIDENCE/environment.txt"
cat /etc/os-release >> "$WMS652_EVIDENCE/environment.txt"
"$WMS652_CHROME" --version >> "$WMS652_EVIDENCE/environment.txt"
sha256sum scripts/ci/wms652-abort-diagnostic/*.mjs > "$WMS652_EVIDENCE/observer-before.sha256"
cp scripts/ci/wms652-abort-diagnostic/*.mjs "$WMS652_EVIDENCE/"
cp docs/evidence/WMS-652/cdp-explicit-abort-preparation-20261007/provenance.json "$WMS652_EVIDENCE/"
set +e
timeout 60s node scripts/ci/wms652-abort-diagnostic/probe.mjs > "$WMS652_EVIDENCE/probe.log" 2>&1
result=$?
set -e
sha256sum scripts/ci/wms652-abort-diagnostic/*.mjs > "$WMS652_EVIDENCE/observer-after.sha256"
cmp "$WMS652_EVIDENCE/observer-before.sha256" "$WMS652_EVIDENCE/observer-after.sha256"
printf '{"probe_exit":%s}\n' "$result" > "$WMS652_EVIDENCE/exit-results.json"
exit "$result"
