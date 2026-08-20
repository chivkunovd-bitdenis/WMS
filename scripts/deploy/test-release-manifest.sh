#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
ARTIFACT_DIR="$(mktemp -d)"
trap 'rm -rf "$ARTIFACT_DIR"' EXIT
RELEASE_SHA="0123456789abcdef0123456789abcdef01234567"
IMAGE_ID="sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"

printf 'backend artifact\n' > "$ARTIFACT_DIR/backend.tar.gz"
printf 'web artifact\n' > "$ARTIFACT_DIR/web.tar.gz"
python3 "$REPO_DIR/scripts/deploy/release_manifest.py" create-offline \
  --release-sha "$RELEASE_SHA" \
  --output "$ARTIFACT_DIR" \
  --backend-archive "$ARTIFACT_DIR/backend.tar.gz" \
  --backend-image "wms-release-backend:${RELEASE_SHA}" \
  --backend-image-id "$IMAGE_ID" \
  --web-archive "$ARTIFACT_DIR/web.tar.gz" \
  --web-image "wms-release-web:${RELEASE_SHA}" \
  --web-image-id "$IMAGE_ID"
python3 "$REPO_DIR/scripts/deploy/release_manifest.py" validate \
  --manifest "$ARTIFACT_DIR/release-manifest.json" \
  --release-sha "$RELEASE_SHA" \
  --artifact-dir "$ARTIFACT_DIR"

printf 'tampered' >> "$ARTIFACT_DIR/backend.tar.gz"
if python3 "$REPO_DIR/scripts/deploy/release_manifest.py" validate \
  --manifest "$ARTIFACT_DIR/release-manifest.json" \
  --release-sha "$RELEASE_SHA" \
  --artifact-dir "$ARTIFACT_DIR"; then
  echo "ERROR: tampered offline artifact was accepted" >&2
  exit 1
fi
echo "release manifest tests passed"
