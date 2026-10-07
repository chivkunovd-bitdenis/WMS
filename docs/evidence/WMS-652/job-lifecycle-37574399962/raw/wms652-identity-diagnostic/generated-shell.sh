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
timeout 600s node frontend/tests-e2e/wms652-critical/browser.identity-diagnostic.untracked.mjs
