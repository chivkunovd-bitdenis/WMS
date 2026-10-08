#!/usr/bin/env bash
# Preserve and restore only the production application images for the WMS-666
# packing UI. Run from /opt/wms on the production host. Database, Redis and all
# volumes are deliberately outside this rollback; no migrations are run.
set -euo pipefail

REPO_DIR="${WMS_REPO_DIR:-/opt/wms}"
STATE_ROOT="${WMS_ROLLBACK_STATE_DIR:-${REPO_DIR}/.deploy-backups/wms666-packing}"
BASE_URL="${WMS_ROLLBACK_BASE_URL:-https://wms.sellerfocus.pro}"
APP_SERVICES=(api celery_worker celery_beat web)
MODE="${1:-}"
RELEASE_SHA="${2:-}"

usage() {
  cat >&2 <<'EOF'
Usage on production host:
  ./scripts/deploy/rollback-wms666-packing.sh prepare <reviewed-release-sha>
  ./scripts/deploy/rollback-wms666-packing.sh seal <reviewed-release-sha>
  ./scripts/deploy/rollback-wms666-packing.sh rollback <reviewed-release-sha>

Run `prepare` immediately before the reviewed deployment and `seal`
immediately after it. Tomorrow, `rollback <reviewed-release-sha>` restores the
API, worker, beat and web images saved by prepare. It refuses if a later
deployment replaced any of those images.
EOF
  exit 2
}

[[ "$MODE" == prepare || "$MODE" == seal || "$MODE" == rollback ]] || usage
[[ "$RELEASE_SHA" =~ ^[0-9a-f]{40}$ ]] || usage
[[ -d "$REPO_DIR" ]] || { echo "ERROR: repository not found: $REPO_DIR" >&2; exit 1; }
cd "$REPO_DIR"

STATE_FILE="${STATE_ROOT}/${RELEASE_SHA}.state"
COMPOSE=(docker compose --env-file /opt/wms/.env -p wms_prod \
  -f /opt/wms/docker-compose.prod.yml \
  -f /opt/wms/docker-compose.wms-host-8088.yml)

current_image_id() {
  local service="$1" container_id
  container_id="$("${COMPOSE[@]}" ps -q "$service")"
  [[ -n "$container_id" ]] || { echo "ERROR: ${service} container is absent" >&2; return 1; }
  docker inspect --format '{{.Image}}' "$container_id"
}

fetch_index_sha() {
  curl --fail --silent --show-error --max-time 12 \
    -H 'Cache-Control: no-cache' \
    "${BASE_URL}/?wms-rollback=${RELEASE_SHA}" | sha256sum | awk '{print $1}'
}

write_state() {
  local status="$1" before_sha="$2" before_index="$3"
  local temporary
  temporary="$(mktemp "${STATE_ROOT}/.state.XXXXXX")"
  chmod 600 "$temporary"
  cat >"$temporary" <<EOF
release_sha=${RELEASE_SHA}
status=${status}
before_source_sha=${before_sha}
before_index_sha=${before_index}
EOF
  for service in "${APP_SERVICES[@]}"; do
    local before_var="${service}_before" deployed_var="${service}_deployed"
    printf '%s=%s\n' "$before_var" "${!before_var}"
    printf '%s=%s\n' "$deployed_var" "${!deployed_var}"
  done >>"$temporary"
  mv "$temporary" "$STATE_FILE"
}

load_state() {
  [[ -f "$STATE_FILE" ]] || { echo "ERROR: no rollback record for ${RELEASE_SHA}" >&2; exit 1; }
  # This file is created locally by this script, root-only, and contains hashes only.
  # shellcheck disable=SC1090
  source "$STATE_FILE"
  [[ "${release_sha:-}" == "$RELEASE_SHA" ]] || { echo "ERROR: rollback record SHA mismatch" >&2; exit 1; }
}

case "$MODE" in
  prepare)
    [[ ! -e "$STATE_FILE" ]] || { echo "ERROR: rollback record already exists: $STATE_FILE" >&2; exit 1; }
    mkdir -p "$STATE_ROOT"
    chmod 700 "$STATE_ROOT"
    for service in "${APP_SERVICES[@]}"; do
      id="$(current_image_id "$service")"
      [[ "$id" =~ ^sha256:[0-9a-f]{64}$ ]] \
        || { echo "ERROR: could not read the current ${service} image" >&2; exit 1; }
      printf -v "${service}_before" '%s' "$id"
      printf -v "${service}_deployed" '%s' "pending"
    done
    before_index="$(fetch_index_sha)"
    [[ "$before_index" =~ ^[0-9a-f]{64}$ ]] \
      || { echo "ERROR: could not fingerprint the current production page" >&2; exit 1; }
    before_sha="$(git rev-parse HEAD)"
    for service in "${APP_SERVICES[@]}"; do
      before_var="${service}_before"
      docker image tag "${!before_var}" "wms666-packing-rollback:${RELEASE_SHA}-${service}"
    done
    write_state prepared "$before_sha" "$before_index"
    echo "Rollback images saved for ${RELEASE_SHA}: ${APP_SERVICES[*]}"
    ;;

  seal)
    load_state
    [[ "$status" == prepared ]] || { echo "ERROR: rollback record is not awaiting seal" >&2; exit 1; }
    [[ "$(git rev-parse HEAD)" == "$RELEASE_SHA" ]] \
      || { echo "ERROR: /opt/wms is not at reviewed release ${RELEASE_SHA}" >&2; exit 1; }
    for service in "${APP_SERVICES[@]}"; do
      id="$(current_image_id "$service")"
      [[ "$id" =~ ^sha256:[0-9a-f]{64}$ ]] \
        || { echo "ERROR: could not read the deployed ${service} image" >&2; exit 1; }
      printf -v "${service}_deployed" '%s' "$id"
    done
    [[ "$web_deployed" != "$web_before" ]] \
      || { echo "ERROR: production web is not running a newly built image" >&2; exit 1; }
    write_state deployed "$before_source_sha" "$before_index_sha"
    echo "Rollback is ready for ${RELEASE_SHA}; application images recorded."
    ;;

  rollback)
    load_state
    if [[ "$status" == rolled_back ]]; then
      for service in "${APP_SERVICES[@]}"; do
        before_var="${service}_before"
        [[ "$(current_image_id "$service")" == "${!before_var}" ]] \
          || { echo "ERROR: a production ${service} image changed after rollback" >&2; exit 1; }
      done
      echo "Already rolled back to the saved application images."
      exit 0
    fi
    [[ "$status" == deployed && "$web_deployed" =~ ^sha256:[0-9a-f]{64}$ ]] \
      || { echo "ERROR: release has not been sealed; refusing an unbounded rollback" >&2; exit 1; }
    for service in "${APP_SERVICES[@]}"; do
      deployed_var="${service}_deployed"
      before_var="${service}_before"
      [[ "$(current_image_id "$service")" == "${!deployed_var}" ]] \
        || { echo "ERROR: production ${service} changed after this release; refusing to undo a later deployment" >&2; exit 1; }
      docker image tag "${!before_var}" "wms_prod-${service}:latest"
    done
    "${COMPOSE[@]}" up -d --no-deps --no-build "${APP_SERVICES[@]}"
    for attempt in {1..30}; do
      all_restored=true
      for service in "${APP_SERVICES[@]}"; do
        before_var="${service}_before"
        [[ "$(current_image_id "$service")" == "${!before_var}" ]] || all_restored=false
      done
      [[ "$all_restored" == true ]] && break
      sleep 1
    done
    for service in "${APP_SERVICES[@]}"; do
      before_var="${service}_before"
      [[ "$(current_image_id "$service")" == "${!before_var}" ]] \
        || { echo "ERROR: the saved ${service} image did not become active" >&2; exit 1; }
    done
    after_index="$(fetch_index_sha)"
    [[ "$after_index" == "$before_index_sha" ]] \
      || { echo "ERROR: production page fingerprint differs from the saved pre-release page" >&2; exit 1; }
    curl --fail --silent --show-error --max-time 12 "${BASE_URL}/api/health" >/dev/null
    write_state rolled_back "$before_source_sha" "$before_index_sha"
    echo "Restored only the saved API, worker, beat and web images. Database, Redis and data volumes were not changed."
    ;;
esac
