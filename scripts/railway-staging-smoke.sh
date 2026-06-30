#!/usr/bin/env bash
# Railway staging smoke — run after deploy. Usage:
#   WMS_STAGING_URL=https://your-web.up.railway.app ./scripts/railway-staging-smoke.sh
set -euo pipefail

BASE="${WMS_STAGING_URL:-}"
if [[ -z "$BASE" ]]; then
  echo "WMS_STAGING_URL is required (public web service URL, no trailing slash)." >&2
  exit 1
fi

BASE="${BASE%/}"
API="${WMS_STAGING_API_URL:-$BASE}"

echo "== smoke: $BASE =="

code_root="$(curl -sS -o /dev/null -w '%{http_code}' "$BASE/")"
echo "GET / -> HTTP $code_root"
[[ "$code_root" == "200" ]] || { echo "FAIL: root not 200" >&2; exit 1; }

code_api="$(curl -sS -o /dev/null -w '%{http_code}' "$API/api/health" 2>/dev/null || echo "000")"
if [[ "$code_api" == "200" ]]; then
  echo "GET /api/health -> HTTP 200"
else
  code_openapi="$(curl -sS -o /dev/null -w '%{http_code}' "$API/api/openapi.json")"
  echo "GET /api/health -> HTTP $code_api (fallback openapi.json -> $code_openapi)"
  [[ "$code_openapi" == "200" ]] || { echo "FAIL: API not reachable" >&2; exit 1; }
fi

html="$(curl -sS "$BASE/")"
if echo "$html" | grep -q 'app-root\|id="root"'; then
  echo "SPA shell: ok"
else
  echo "WARN: root HTML may not be SPA (check Caddy/web build)"
fi

echo "== smoke passed =="
