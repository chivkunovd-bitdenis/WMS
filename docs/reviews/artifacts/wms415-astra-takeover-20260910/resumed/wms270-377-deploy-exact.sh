#!/usr/bin/env bash
set -euo pipefail
: "${WMS270_TARGET_SHA:?exact merged target required}"
cd /opt/wms
require_200() {
  local code
  code="$(curl --fail --silent --show-error --retry 10 --retry-connrefused --retry-delay 2 --max-time 15 --output /dev/null --write-out '%{http_code}' "$1")"
  test "$code" = 200
}
BASE_SHA=120b106cc3f47dd28fa499e094c7cde83e8a6b40
tracked_changes="$(git status --porcelain --untracked-files=no)"
test -z "$tracked_changes"
untracked_sources="$(git ls-files --others --exclude-standard -- backend/app frontend)"
test -z "$untracked_sources"
git -c protocol.version=1 -c http.version=HTTP/1.1 fetch origin etalon </dev/null
test "$(git rev-parse HEAD)" = "$BASE_SHA"
test "$(git rev-parse origin/etalon)" = "$WMS270_TARGET_SHA"
git merge-base --is-ancestor "$BASE_SHA" "$WMS270_TARGET_SHA"
EXPECTED_APP=$'backend/app/api/auth.py\nbackend/app/services/auth_service.py\nbackend/app/services/login_rate_limit.py'
test "$(git diff --name-only "$BASE_SHA" "$WMS270_TARGET_SHA" -- backend/app)" = "$EXPECTED_APP"
excluded_changes="$(git diff --name-only "$BASE_SHA" "$WMS270_TARGET_SHA" -- frontend backend/alembic docker-compose.prod.yml)"
test -z "$excluded_changes"
COMPOSE=(docker compose -p wms_prod -f docker-compose.prod.yml -f docker-compose.wms-host-8088.yml)
DB_CONTAINER="$("${COMPOSE[@]}" ps -a -q db)"
test "$(docker inspect "$DB_CONTAINER" --format '{{index .Config.Labels "com.docker.compose.project"}}')" = wms_prod
for name in api web; do
  docker inspect "wms_prod-$name-1" --format '{{.Name}} before_image={{.Image}} before_started={{.State.StartedAt}}'
done
git checkout -B etalon "$WMS270_TARGET_SHA"
python3 scripts/deploy/verify-wms-host-network.py "$DB_CONTAINER"
# No schema change: no migration, database restart or writer-wide shutdown.
for service in api web; do
  echo "WMS270 building $service from $WMS270_TARGET_SHA"
  "${COMPOSE[@]}" build "$service" </dev/null
done
test "$(git rev-parse HEAD)" = "$WMS270_TARGET_SHA"
tracked_changes="$(git status --porcelain --untracked-files=no)"
test -z "$tracked_changes"
"${COMPOSE[@]}" up -d --no-deps api web </dev/null
for path in / /seller/ /api/health; do
  require_200 "https://wms.sellerfocus.pro$path"
  echo "WMS270 HTTPS200 $path"
done
require_200 http://172.18.0.1:8088/seller/
LEGACY="$(docker ps -q --filter 'label=com.docker.compose.project=wms_prod' --filter 'label=com.docker.compose.service=web_seller')"
while IFS= read -r container; do
  if [[ -n "$container" ]]; then docker stop "$container" </dev/null; fi
done <<< "$LEGACY"
python3 scripts/deploy/verify-wms-host-network.py "$DB_CONTAINER"
for path in / /seller/ /api/health; do
  require_200 "https://wms.sellerfocus.pro$path"
  echo "WMS270 final HTTPS200 $path"
done
for name in api web celery_worker celery_beat; do
  docker inspect "wms_prod-$name-1" --format '{{.Name}} image={{.Image}} started={{.State.StartedAt}} running={{.State.Running}}'
done
git rev-parse HEAD
