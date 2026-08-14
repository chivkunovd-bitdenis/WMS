#!/usr/bin/env bash
set -euo pipefail

ROOT="/Users/deniscivkunov/Projects/WMS/.worktrees/product-operations-ux-20260812"
EVIDENCE="$ROOT/docs/reviews/product-operations-ux/2026-08-12/evidence/final-browser-regression-rerun-catalog-live-strict"
RUN_ID="$(date +%Y%m%d-%H%M%S)"
RUN_DIR="$EVIDENCE/run-$RUN_ID"

API_PORT="${CATALOG_RERUN_API_PORT:-18591}"
WEB_PORT="${CATALOG_RERUN_WEB_PORT:-15591}"
EMU_PORT="${CATALOG_RERUN_EMU_PORT:-18592}"

PY="$ROOT/backend/.venv/bin/python"
if [[ ! -x "$PY" ]]; then
  PY="python3"
fi

mkdir -p "$RUN_DIR"
rm -f "$RUN_DIR/wms.sqlite" "$RUN_DIR/wb_emulator.sqlite"

API_PID=""
WEB_PID=""
EMU_PID=""

cleanup() {
  for pid in "$WEB_PID" "$API_PID" "$EMU_PID"; do
    if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null || true
    fi
  done
}
trap cleanup EXIT

wait_http() {
  local url="$1"
  local label="$2"
  for _ in {1..90}; do
    if curl --fail --silent "$url" >/dev/null; then
      return 0
    fi
    sleep 1
  done
  echo "Timed out waiting for $label at $url" >&2
  return 1
}

(
  cd "$ROOT"
  WB_EMULATOR_DB_PATH="$RUN_DIR/wb_emulator.sqlite" \
  WB_EMULATOR_TOKEN_MAP='{"catalog-rerun-token":"catalog_rerun_seller"}' \
  WB_EMULATOR_ADMIN_TOKEN="catalog-rerun-admin-token" \
    "$PY" -m uvicorn wb_emulator.main:app --host 127.0.0.1 --port "$EMU_PORT"
) >"$RUN_DIR/emulator.log" 2>&1 &
EMU_PID="$!"
wait_http "http://127.0.0.1:$EMU_PORT/health" "WB emulator"

(
  cd "$ROOT/backend"
  WMS_AUTO_CREATE_SCHEMA=1 \
  DATABASE_URL="sqlite+aiosqlite:///$RUN_DIR/wms.sqlite" \
  JWT_SECRET_KEY="catalog-rerun-jwt-secret-key-minimum-32-chars" \
  WILDBERRIES_MARKETPLACE_API_BASE="http://127.0.0.1:$EMU_PORT" \
  E2E_MOCK_WB_CARDS=1 \
  E2E_MOCK_WB_SUPPLIES=1 \
  E2E_MOCK_WB_WAREHOUSES=1 \
    "$PY" -m uvicorn app.main:app --host 127.0.0.1 --port "$API_PORT"
) >"$RUN_DIR/api.log" 2>&1 &
API_PID="$!"
wait_http "http://127.0.0.1:$API_PORT/health" "WMS API"

(
  cd "$ROOT/frontend"
  VITE_API_PROXY="http://127.0.0.1:$API_PORT" \
  E2E_SELLER_PATH_PREFIX="/seller" \
  VITE_SELLER_PORTAL_URL="http://127.0.0.1:$WEB_PORT/seller/" \
    npm run dev -- --host 127.0.0.1 --port "$WEB_PORT"
) >"$RUN_DIR/web.log" 2>&1 &
WEB_PID="$!"
wait_http "http://127.0.0.1:$WEB_PORT/" "Vite web"

(
  cd "$ROOT"
  CATALOG_RERUN_API_ORIGIN="http://127.0.0.1:$API_PORT" \
  CATALOG_RERUN_WEB_ORIGIN="http://127.0.0.1:$WEB_PORT" \
  CATALOG_RERUN_EMULATOR_ORIGIN="http://127.0.0.1:$EMU_PORT" \
  CATALOG_RERUN_EVIDENCE_DIR="$EVIDENCE" \
  CATALOG_RERUN_RUN_DIR="$RUN_DIR" \
  CATALOG_RERUN_WMS_DB_PATH="$RUN_DIR/wms.sqlite" \
  CATALOG_RERUN_API_PORT="$API_PORT" \
  CATALOG_RERUN_WEB_PORT="$WEB_PORT" \
  CATALOG_RERUN_EMU_PORT="$EMU_PORT" \
    node "$EVIDENCE/final_browser_regression_rerun_catalog_live_strict.mjs"
) 2>&1 | tee "$RUN_DIR/qa-console.log"

echo "$EVIDENCE/FINAL_BROWSER_REGRESSION_RERUN_CATALOG_LIVE_STRICT_RU.md"
