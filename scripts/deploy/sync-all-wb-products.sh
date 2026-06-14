#!/usr/bin/env bash
# Full WB cards → size-variant products for every seller with a content token.
# Run on prod after deploy (from repo root), e.g.:
#   ./scripts/deploy/sync-all-wb-products.sh
set -euo pipefail

REPO_DIR="${WMS_REPO_DIR:-$(cd "$(dirname "$0")/../.." && pwd)}"
cd "$REPO_DIR"

COMPOSE=(docker compose -f docker-compose.prod.yml)
if [[ -f docker-compose.wms-host-8088.yml ]]; then
  COMPOSE+=(-f docker-compose.wms-host-8088.yml)
fi

echo "==> WB products sync (all sellers with content token)"
"${COMPOSE[@]}" exec -T api python -m app.cli.sync_all_wb_products

echo "Done."
