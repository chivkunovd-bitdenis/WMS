#!/usr/bin/env bash
# Run on the production server from the repo root (e.g. /opt/wms).
set -euo pipefail

REPO_DIR="${WMS_REPO_DIR:-$(cd "$(dirname "$0")/../.." && pwd)}"
cd "$REPO_DIR"

# Deploy SSH user may differ from repo owner (git 2.35+ safe.directory).
git config --global --add safe.directory "$REPO_DIR"

if [[ -z "${WMS_RELEASE_SHA:-}" ]]; then
  echo "ERROR: WMS_RELEASE_SHA is required; production deploy must name the approved exact SHA." >&2
  exit 64
fi
if [[ ! "$WMS_RELEASE_SHA" =~ ^[0-9a-f]{40}$ ]]; then
  echo "ERROR: WMS_RELEASE_SHA must be a lowercase 40-char Git SHA." >&2
  exit 64
fi

CURRENT_SHA="$(git rev-parse HEAD)"
if [[ "$CURRENT_SHA" != "$WMS_RELEASE_SHA" ]]; then
  echo "ERROR: deploy checkout mismatch: HEAD=$CURRENT_SHA, WMS_RELEASE_SHA=$WMS_RELEASE_SHA" >&2
  exit 65
fi
if [[ -n "$(git status --porcelain)" ]]; then
  echo "ERROR: production worktree is dirty; exact-SHA deploy refuses to continue." >&2
  git status --short
  exit 66
fi

export WMS_GIT_SHA="$WMS_RELEASE_SHA"
export WMS_ARTIFACT_DIGEST="${WMS_ARTIFACT_DIGEST:-server-build:${WMS_RELEASE_SHA}}"

COMPOSE=(docker compose -f docker-compose.prod.yml)
if [[ -f docker-compose.wms-host-8088.yml ]]; then
  COMPOSE+=(-f docker-compose.wms-host-8088.yml)
fi

BUILD_SERVICES=(migrations api celery_worker celery_beat web)

echo "==> docker compose prod build (sequential)"
for service in "${BUILD_SERVICES[@]}"; do
  "${COMPOSE[@]}" build "$service"
done

echo "==> start infrastructure"
"${COMPOSE[@]}" up -d --wait db redis

echo "==> run database migrations"
"${COMPOSE[@]}" run --rm migrations

echo "==> start application services"
"${COMPOSE[@]}" up -d --no-deps api celery_worker celery_beat web

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
