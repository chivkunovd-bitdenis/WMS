#!/usr/bin/env bash
set -euo pipefail

ROOT="/Users/deniscivkunov/Projects/WMS/.worktrees/product-operations-ux-20260812"
EVIDENCE="$ROOT/docs/reviews/product-operations-ux/2026-08-12/evidence/f22-browser-product-qa-after-read-model"
SCENARIO="$ROOT/docs/reviews/product-operations-ux/2026-08-12/evidence/f22-browser-product-qa-after-read-model/f22_browser_product_qa_after_read_model.mjs"
RUN_ID="$(date +%Y%m%d-%H%M%S)"
RUN_DIR="$EVIDENCE/run-$RUN_ID"

API_PORT="${F22_API_PORT:-18222}"
WEB_PORT="${F22_WEB_PORT:-15222}"
EMU_PORT="${F22_EMU_PORT:-18223}"

mkdir -p "$RUN_DIR"

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

rm -f "$RUN_DIR/wms.sqlite" "$RUN_DIR/wb_emulator.sqlite"

(
  cd "$ROOT"
  WB_EMULATOR_DB_PATH="$RUN_DIR/wb_emulator.sqlite" \
  WB_EMULATOR_TOKEN_MAP='{"f22-safe-token":"f22_seller"}' \
  WB_EMULATOR_ADMIN_TOKEN="f22-admin-token" \
    backend/.venv/bin/python -m uvicorn wb_emulator.main:app --host 127.0.0.1 --port "$EMU_PORT"
) >"$RUN_DIR/emulator.log" 2>&1 &
EMU_PID="$!"
wait_http "http://127.0.0.1:$EMU_PORT/health" "WB emulator"

(
  cd "$ROOT/backend"
  WMS_AUTO_CREATE_SCHEMA=1 \
  DATABASE_URL="sqlite+aiosqlite:///$RUN_DIR/wms.sqlite" \
  JWT_SECRET_KEY="f22-browser-qa-jwt-secret-key-minimum-32-chars" \
  WILDBERRIES_MARKETPLACE_API_BASE="http://127.0.0.1:$EMU_PORT" \
  E2E_MOCK_WB_CARDS=1 \
  E2E_MOCK_WB_SUPPLIES=1 \
  E2E_MOCK_WB_WAREHOUSES=1 \
    .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port "$API_PORT"
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
  F22_API_ORIGIN="http://127.0.0.1:$API_PORT" \
  F22_WEB_ORIGIN="http://127.0.0.1:$WEB_PORT" \
  F22_EMULATOR_ORIGIN="http://127.0.0.1:$EMU_PORT" \
  F22_EVIDENCE_DIR="$RUN_DIR" \
  F22_WMS_DB_PATH="$RUN_DIR/wms.sqlite" \
    node "$SCENARIO"
) 2>&1 | tee "$RUN_DIR/qa-console.log"

echo "$RUN_DIR"
