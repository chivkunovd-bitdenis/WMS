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

if [[ -z "${WMS_RELEASE_MANIFEST:-}" ]]; then
  echo "ERROR: WMS_RELEASE_MANIFEST is required; production deploy accepts only a verified offline release artifact." >&2
  exit 67
fi
if [[ -z "${WMS_RELEASE_ARTIFACT_DIR:-}" ]]; then
  echo "ERROR: WMS_RELEASE_ARTIFACT_DIR is required with WMS_RELEASE_MANIFEST." >&2
  exit 67
fi

MANIFEST_TOOL="$REPO_DIR/scripts/deploy/release_manifest.py"
MANIFEST_DIR="$(cd "$(dirname "$WMS_RELEASE_MANIFEST")" && pwd)"
ARTIFACT_DIR="$(cd "$WMS_RELEASE_ARTIFACT_DIR" && pwd)"
if [[ "$MANIFEST_DIR" != "$ARTIFACT_DIR" ]]; then
  echo "ERROR: release manifest and offline artifact files must be in the same directory." >&2
  exit 67
fi
if [[ ! -f "$MANIFEST_TOOL" ]]; then
  echo "ERROR: release manifest validator is missing: $MANIFEST_TOOL" >&2
  exit 67
fi

mapfile -t RELEASE_ARTIFACTS < <(
  python3 "$MANIFEST_TOOL" metadata \
    --manifest "$WMS_RELEASE_MANIFEST" \
    --release-sha "$WMS_RELEASE_SHA" \
    --artifact-dir "$ARTIFACT_DIR"
)
if [[ "${#RELEASE_ARTIFACTS[@]}" -ne 2 ]]; then
  echo "ERROR: release manifest did not provide backend and web artifacts." >&2
  exit 67
fi

BACKEND_IMAGE=""
WEB_IMAGE=""
for artifact in "${RELEASE_ARTIFACTS[@]}"; do
  IFS=$'\t' read -r artifact_name archive_name archive_digest image_name image_id <<< "$artifact"
  case "$artifact_name" in
    backend) BACKEND_IMAGE="$image_name" ;;
    web) WEB_IMAGE="$image_name" ;;
    *)
      echo "ERROR: unexpected artifact name from manifest: $artifact_name" >&2
      exit 67
      ;;
  esac

  echo "==> load verified ${artifact_name} image (${archive_digest})"
  docker load --input "$ARTIFACT_DIR/$archive_name"
  loaded_image_id="$(docker image inspect --format '{{.Id}}' "$image_name")"
  if [[ "$loaded_image_id" != "$image_id" ]]; then
    echo "ERROR: loaded ${artifact_name} image ID mismatch: expected $image_id, got $loaded_image_id" >&2
    exit 67
  fi
done
if [[ -z "$BACKEND_IMAGE" || -z "$WEB_IMAGE" ]]; then
  echo "ERROR: release manifest must define backend and web image references." >&2
  exit 67
fi

MANIFEST_DIGEST="sha256:$(sha256sum "$WMS_RELEASE_MANIFEST" | awk '{print $1}')"
export WMS_ARTIFACT_DIGEST="$MANIFEST_DIGEST"

RELEASE_COMPOSE_OVERRIDE="$(mktemp "${TMPDIR:-/tmp}/wms-release-images.XXXXXX.yml")"
trap 'rm -f "$RELEASE_COMPOSE_OVERRIDE"' EXIT
cat > "$RELEASE_COMPOSE_OVERRIDE" <<EOF
services:
  api:
    build: null
    image: $BACKEND_IMAGE
  migrations:
    build: null
    image: $BACKEND_IMAGE
  celery_worker:
    build: null
    image: $BACKEND_IMAGE
  celery_beat:
    build: null
    image: $BACKEND_IMAGE
  web:
    build: null
    image: $WEB_IMAGE
EOF

COMPOSE=(docker compose -f docker-compose.prod.yml)
if [[ -f docker-compose.wms-host-8088.yml ]]; then
  COMPOSE+=(-f docker-compose.wms-host-8088.yml)
fi
COMPOSE+=(-f "$RELEASE_COMPOSE_OVERRIDE")

echo "==> start infrastructure"
"${COMPOSE[@]}" up -d --wait db redis

echo "==> run database migrations"
"${COMPOSE[@]}" run --rm migrations

echo "==> start application services"
"${COMPOSE[@]}" up -d --no-build --no-deps api celery_worker celery_beat web

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
