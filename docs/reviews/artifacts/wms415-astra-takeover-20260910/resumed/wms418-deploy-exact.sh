#!/usr/bin/env bash
set -euo pipefail
: "${WMS418_TARGET_SHA:?exact reviewed and merged target required}"
cd /opt/wms
BASE_SHA=eaa6ae9aecee875c50b31afa6b2cc224bb57d043
test -z "$(git status --porcelain --untracked-files=no)"
git -c protocol.version=1 -c http.version=HTTP/1.1 fetch origin etalon
test "$(git rev-parse HEAD)" = "$BASE_SHA"
test "$(git rev-parse origin/etalon)" = "$WMS418_TARGET_SHA"
git merge-base --is-ancestor "$BASE_SHA" "$WMS418_TARGET_SHA"
EXPECTED_APP_FILES=$'backend/app/api/products.py\nbackend/app/services/seller_wb_catalog_service.py\nfrontend/src/screens/v2/FfProductsCatalogScreen.tsx'
test "$(git diff --name-only "$BASE_SHA" "$WMS418_TARGET_SHA" -- backend/app frontend)" = "$EXPECTED_APP_FILES"
test -z "$(git diff --name-only "$BASE_SHA" "$WMS418_TARGET_SHA" -- backend/alembic docker-compose.yml docker-compose.prod.yml docker-compose.wms-host-8088.yml deploy scripts/deploy .github/workflows/deploy.yml)"
test "$(docker inspect wms_prod-api-1 --format '{{index .Config.Labels "com.docker.compose.project"}}')" = wms_prod
API_BEFORE=$(docker inspect wms_prod-api-1 --format '{{.Image}}')
WEB_BEFORE=$(docker inspect wms_prod-web-1 --format '{{.Image}}')
printf 'WMS418 base=%s api_before=%s web_before=%s\n' "$BASE_SHA" "$API_BEFORE" "$WEB_BEFORE"
git checkout -B etalon "$WMS418_TARGET_SHA"
COMPOSE=(docker compose -p wms_prod -f docker-compose.prod.yml -f docker-compose.wms-host-8088.yml)
for service in api web; do
  echo "WMS418 building $service from $WMS418_TARGET_SHA"
  "${COMPOSE[@]}" build "$service" </dev/null
done
test "$(git rev-parse HEAD)" = "$WMS418_TARGET_SHA"
test -z "$(git status --porcelain --untracked-files=no)"
echo "WMS418 restart only api/web; no dependencies or migrations"
"${COMPOSE[@]}" up -d --no-deps api web </dev/null
for path in / /seller/ /api/health /api/openapi.json; do
  curl --fail --silent --show-error --retry 10 --retry-connrefused --retry-delay 2 --max-time 15 "https://wms.sellerfocus.pro$path" > /dev/null
  echo "WMS418 HTTPS200 $path"
done
for container in wms_prod-api-1 wms_prod-web-1 wms_prod-celery_worker-1 wms_prod-celery_beat-1; do
  docker inspect "$container" --format '{{.Name}} image={{.Image}} started={{.State.StartedAt}} running={{.State.Running}}'
done
git rev-parse HEAD
