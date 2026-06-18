#!/usr/bin/env bash
# Run on the production server from the repo root (e.g. /opt/wms).
# Preconditions: code already merged to origin/main via PR; CI on main is green.
set -euo pipefail

REPO_DIR="${WMS_REPO_DIR:-$(cd "$(dirname "$0")/../.." && pwd)}"
cd "$REPO_DIR"

echo "==> git pull"
git fetch origin
git checkout main
git pull --ff-only origin main

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
  ./scripts/deploy/sync-all-wb-products.sh
else
  echo "skip: scripts/deploy/sync-all-wb-products.sh not found"
fi

echo "Done. Check https://${WMS_PUBLIC_DOMAIN:-your-domain}"
