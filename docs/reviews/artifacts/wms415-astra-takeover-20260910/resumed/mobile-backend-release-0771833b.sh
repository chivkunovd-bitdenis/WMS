#!/usr/bin/env bash
set -euo pipefail
cd /opt/wms
TARGET_SHA=0771833b7389260042f03a47abc7821e3a47fcb4
BASE_SHA=0229831f7442823f086f0147ffa85aed05b8ca66
test -z "$(git status --porcelain --untracked-files=no)"
git -c protocol.version=1 -c http.version=HTTP/1.1 fetch origin etalon
git merge-base --is-ancestor "$TARGET_SHA" origin/etalon
test "$(git rev-parse HEAD)" = "$BASE_SHA"
test -z "$(git diff --name-only "$BASE_SHA" "$TARGET_SHA" -- backend/alembic frontend docker-compose.prod.yml scripts/deploy)"
test "$(docker inspect wms_prod-api-1 --format '{{index .Config.Labels "com.docker.compose.project"}}')" = wms_prod
git checkout -B etalon "$TARGET_SHA"
echo "WMS_DEPLOY checked-out $TARGET_SHA"
COMPOSE=(docker compose -p wms_prod -f docker-compose.prod.yml -f docker-compose.wms-host-8088.yml)
for service in api celery_worker celery_beat; do
  echo "WMS_DEPLOY building $service"
  "${COMPOSE[@]}" build "$service" </dev/null
done
echo "WMS_DEPLOY restarting backend services only"
"${COMPOSE[@]}" up -d --no-deps api celery_worker celery_beat </dev/null
echo "WMS_DEPLOY backend started $TARGET_SHA"
"${COMPOSE[@]}" ps api celery_worker celery_beat
git rev-parse HEAD
