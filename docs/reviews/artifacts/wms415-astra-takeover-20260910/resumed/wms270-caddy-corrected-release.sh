#!/usr/bin/env bash
set -euo pipefail
: "${WMS270_TARGET_SHA:?exact merged SHA required}"
phase="${1:?load or activate required}"
BASE=1922a2242ad626a9618cb2b7300e6cf500d25b4d
RECOVERY=sha256:5b0f5e9d44786522ec343c805c43903256abe44ee692c0f06bca7a0521d61517
AUTH=sha256:fe66c88c44f9fe346a4dda34b59f6dcf76cf3149b75e8ed9296f5f4570d5aaab
cd /opt/wms
require_200() {
 local code
 code="$(curl --fail --silent --show-error --retry 5 --retry-all-errors --retry-delay 1 --max-time 15 --output /dev/null --write-out '%{http_code}' "$1")"
 test "$code" = 200
}
test "$phase" = load || test "$phase" = activate
tracked="$(git status --porcelain --untracked-files=no)"; test -z "$tracked"
test "$(git rev-parse HEAD)" = "$BASE"
git fetch origin etalon </dev/null
test "$(git rev-parse origin/etalon)" = "$WMS270_TARGET_SHA"
git merge-base --is-ancestor "$BASE" "$WMS270_TARGET_SHA"
changed="$(git diff --name-only "$BASE" "$WMS270_TARGET_SHA" -- backend frontend docker-compose.prod.yml docker-compose.wms-host-8088.yml scripts/deploy/prod-update.sh scripts/deploy/verify-wms-host-network.py)"
test -z "$changed"
test "$(git diff --name-only "$BASE" "$WMS270_TARGET_SHA" -- deploy)" = deploy/Caddyfile.http
test "$(docker inspect wms_prod-api-1 --format '{{.Image}}')" = "$RECOVERY"
test "$(docker exec wms_prod-web-1 caddy version | cut -d' ' -f1)" = v2.11.2
candidate="$(git show "$WMS270_TARGET_SHA:deploy/Caddyfile.http")"
printf '%s\n' "$candidate" | docker exec -i wms_prod-web-1 caddy validate --config - --adapter caddyfile
require_200 https://wms.sellerfocus.pro/api/health
if [[ "$phase" = load ]]; then
 # Graceful live reload only. The mounted on-disk file remains BASE until activate.
 printf '%s\n' "$candidate" | docker exec -i wms_prod-web-1 caddy reload --config - --adapter caddyfile
 test "$(docker inspect wms_prod-api-1 --format '{{.Image}}')" = "$RECOVERY"
 require_200 https://wms.sellerfocus.pro/api/health
 echo "WMS270_PHASE loaded $WMS270_TARGET_SHA API_RECOVERY_RETAINED"
 exit 0
fi
# Root must provide a fresh successful four-health-GET proof before activation.
: "${WMS270_CHAIN_VERIFIED_SHA:?successful two-origin health proof required}"
test "$WMS270_CHAIN_VERIFIED_SHA" = "$WMS270_TARGET_SHA"
test "$(docker image inspect wms-security-api:1922a224 --format '{{.Id}}')" = "$AUTH"
# App and frontend sources are unchanged from BASE. Existing exact images are reused.
git checkout -B etalon "$WMS270_TARGET_SHA"
COMPOSE=(docker compose -p wms_prod -f docker-compose.prod.yml -f docker-compose.wms-host-8088.yml)
rollback_api() {
 docker image tag "$RECOVERY" wms_prod-api:latest
 "${COMPOSE[@]}" up -d --no-deps --no-build api </dev/null
 echo WMS270_API_RECOVERY_RESTORED >&2
}
trap rollback_api ERR
docker image tag "$AUTH" wms_prod-api:latest
# Refresh the read-only bind mount inode and API; no port/address/config expansion.
"${COMPOSE[@]}" up -d --no-deps --no-build --force-recreate api web </dev/null
for path in / /seller/ /api/health; do require_200 "https://wms.sellerfocus.pro$path"; done
test "$(docker inspect wms_prod-api-1 --format '{{.Image}}')" = "$AUTH"
tracked="$(git status --porcelain --untracked-files=no)"; test -z "$tracked"
trap - ERR
echo "WMS270_PHASE activated $WMS270_TARGET_SHA"
