#!/usr/bin/env bash
# Run on the production server from the repo root (e.g. /opt/wms).
set -euo pipefail

REPO_DIR="${WMS_REPO_DIR:-$(cd "$(dirname "$0")/../.." && pwd)}"
cd "$REPO_DIR"

# Deploy SSH user may differ from repo owner (git 2.35+ safe.directory).
git config --global --add safe.directory "$REPO_DIR"

echo "==> git pull"
git fetch origin
git checkout main
if ! git pull --ff-only origin main; then
  echo "WARN: pull blocked by local changes; resetting to origin/main"
  git reset --hard origin/main
fi

COMPOSE=(docker compose -f docker-compose.prod.yml)
if [[ -f docker-compose.wms-host-8088.yml ]]; then
  COMPOSE+=(-f docker-compose.wms-host-8088.yml)
fi

echo "==> docker compose prod build & up"
"${COMPOSE[@]}" build
"${COMPOSE[@]}" up -d

echo "==> status"
"${COMPOSE[@]}" ps

echo "==> WB products re-sync (all sellers; legacy SKUs → OLD/…)"
if [[ -x scripts/deploy/sync-all-wb-products.sh ]]; then
  if ! ./scripts/deploy/sync-all-wb-products.sh; then
    sync_rc=$?
    echo "WARN: WB products sync failed (exit ${sync_rc}; 137 often OOM) — deploy continues."
    echo "      Re-run later: ./scripts/deploy/sync-all-wb-products.sh"
  fi
else
  echo "skip: scripts/deploy/sync-all-wb-products.sh not found"
fi

echo "Done. Check https://${WMS_PUBLIC_DOMAIN:-your-domain}"
