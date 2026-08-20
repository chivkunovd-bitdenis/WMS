#!/usr/bin/env bash
# Build each production image once in CI and package an offline promotion artifact.
set -euo pipefail

usage() {
  echo "Usage: $0 --release-sha <40-char-sha> --output <artifact-directory>" >&2
  exit 64
}

RELEASE_SHA=""
OUTPUT_DIR=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --release-sha) RELEASE_SHA="${2:-}"; shift 2 ;;
    --output) OUTPUT_DIR="${2:-}"; shift 2 ;;
    *) usage ;;
  esac
done

if [[ ! "$RELEASE_SHA" =~ ^[0-9a-f]{40}$ ]] || [[ -z "$OUTPUT_DIR" ]]; then
  usage
fi

REPO_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
OUTPUT_DIR="$(mkdir -p "$OUTPUT_DIR" && cd "$OUTPUT_DIR" && pwd)"
BACKEND_IMAGE="wms-release-backend:${RELEASE_SHA}"
WEB_IMAGE="wms-release-web:${RELEASE_SHA}"

cd "$REPO_DIR"
docker build --label "org.opencontainers.image.revision=${RELEASE_SHA}" --tag "$BACKEND_IMAGE" backend
docker build --label "org.opencontainers.image.revision=${RELEASE_SHA}" --file frontend/Dockerfile.prod --tag "$WEB_IMAGE" .

docker save "$BACKEND_IMAGE" | gzip -n > "$OUTPUT_DIR/backend.tar.gz"
docker save "$WEB_IMAGE" | gzip -n > "$OUTPUT_DIR/web.tar.gz"

BACKEND_IMAGE_ID="$(docker image inspect --format '{{.Id}}' "$BACKEND_IMAGE")"
WEB_IMAGE_ID="$(docker image inspect --format '{{.Id}}' "$WEB_IMAGE")"
python3 scripts/deploy/release_manifest.py create-offline \
  --release-sha "$RELEASE_SHA" \
  --output "$OUTPUT_DIR" \
  --backend-archive "$OUTPUT_DIR/backend.tar.gz" \
  --backend-image "$BACKEND_IMAGE" \
  --backend-image-id "$BACKEND_IMAGE_ID" \
  --web-archive "$OUTPUT_DIR/web.tar.gz" \
  --web-image "$WEB_IMAGE" \
  --web-image-id "$WEB_IMAGE_ID"
