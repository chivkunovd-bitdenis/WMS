#!/usr/bin/env bash
# Run on the production server from the repo root (e.g. /opt/wms).
set -euo pipefail

REPO_DIR="${WMS_REPO_DIR:-$(cd "$(dirname "$0")/../.." && pwd)}"
cd "$REPO_DIR"

# Deploy SSH user may differ from repo owner (git 2.35+ safe.directory).
git config --global --add safe.directory "$REPO_DIR"

DEPLOY_REMOTE="${WMS_DEPLOY_REMOTE:-origin}"
DEPLOY_BRANCH="${WMS_DEPLOY_BRANCH:-etalon}"
DEPLOY_TRUNK_REF="${WMS_DEPLOY_TRUNK_REF:-${DEPLOY_REMOTE}/etalon}"
DEPLOY_TARGET_REF="${DEPLOY_REMOTE}/${DEPLOY_BRANCH}"

# Optional pin (WMS-641): deploy exactly this commit instead of the branch head.
# Empty or unset keeps the previous behaviour. The trunk guard below still applies,
# so the pinned commit must be contained in the trunk.
if [[ -n "${WMS_DEPLOY_SHA:-}" ]]; then
  if [[ ! "${WMS_DEPLOY_SHA}" =~ ^[0123456789abcdef]{40}$ ]]; then
    echo "ERROR: WMS_DEPLOY_SHA must be a full 40-character lowercase commit id." >&2
    exit 1
  fi
  DEPLOY_TARGET_REF="${WMS_DEPLOY_SHA}"
fi

echo "==> git fetch"
# Протокол v2 с боевого сервера ломается: GitHub отвечает 401, git просит логин
# и падает с «expected flush after ref listing» — при том что репозиторий
# публичный и curl тот же адрес отдаёт 200. Выкатка 02.09.2026 встала на этом
# дважды подряд. На v1 тот же fetch проходит мгновенно, поэтому фиксируем версию
# протокола явно, а не гадаем, вернётся ли v2 сам.
# И HTTP/1.1 поверх этого. 02.09.2026 выкатка встала снова, уже с другой
# половиной той же беды: `ls-remote` проходил, а `fetch` падал тем же «could
# not read Username». Виноват HTTP/2 — по нему GitHub с этого сервера отвечает
# на POST 401, и git идёт спрашивать логин, которого тут нет и не должно быть.
# На HTTP/1.1 тот же fetch проходит сразу. Проверено перебором: v0, v1 и v2
# протокола падают одинаково, а смена версии HTTP чинит все три.
git -c protocol.version=1 -c http.version=HTTP/1.1 fetch --prune "$DEPLOY_REMOTE"

if ! git rev-parse --verify --quiet "${DEPLOY_TRUNK_REF}^{commit}" >/dev/null; then
  echo "ERROR: deploy trunk ref '${DEPLOY_TRUNK_REF}' was not found." >&2
  echo "       Production deploy is allowed only from the configured trunk." >&2
  exit 1
fi

if ! git rev-parse --verify --quiet "${DEPLOY_TARGET_REF}^{commit}" >/dev/null; then
  echo "ERROR: deploy target ref '${DEPLOY_TARGET_REF}' was not found." >&2
  exit 1
fi

echo "==> checkout deploy branch"
git checkout -B "$DEPLOY_BRANCH" "$DEPLOY_TARGET_REF"

# A pinned deploy must land exactly on the requested commit; stop before any build otherwise.
if [[ -n "${WMS_DEPLOY_SHA:-}" && "$(git rev-parse HEAD)" != "${WMS_DEPLOY_SHA}" ]]; then
  echo "ERROR: pinned deploy requested ${WMS_DEPLOY_SHA} but HEAD is $(git rev-parse HEAD)." >&2
  exit 1
fi

DEPLOY_SHA="$(git rev-parse HEAD)"
TRUNK_SHA="$(git rev-parse "$DEPLOY_TRUNK_REF")"

echo "==> deploy guard"
echo "    target: ${DEPLOY_BRANCH} @ ${DEPLOY_SHA:0:12}"
echo "    trunk:  ${DEPLOY_TRUNK_REF} @ ${TRUNK_SHA:0:12}"

if ! git merge-base --is-ancestor "$DEPLOY_SHA" "$TRUNK_SHA"; then
  echo "ERROR: refusing production deploy from '${DEPLOY_BRANCH}'." >&2
  echo "       Commit ${DEPLOY_SHA} is not contained in trunk '${DEPLOY_TRUNK_REF}'." >&2
  echo "       Merge the change into trunk first, then deploy the trunk commit." >&2
  exit 1
fi

if [[ "${WMS_DEPLOY_GUARD_ONLY:-0}" == "1" ]]; then
  echo "Deploy guard passed; WMS_DEPLOY_GUARD_ONLY=1, stopping before build."
  exit 0
fi

# Server independently verifies exact etalon CI and current process-proof metadata.
# Failure (including unavailable public API) stops before any Docker action.
echo "==> verify exact server process CI"
python3 scripts/ci/verify_server_process_ci.py --sha "$DEPLOY_SHA"

COMPOSE=(docker compose -f docker-compose.prod.yml)
if [[ -f docker-compose.wms-host-8088.yml ]]; then
  COMPOSE+=(-f docker-compose.wms-host-8088.yml)
  # Fail before build, writer shutdown or DDL if Docker recreated either bridge.
  echo "==> verify existing private proxy topology"
  DB_CONTAINER="$("${COMPOSE[@]}" ps -a -q db)"
  python3 scripts/deploy/verify-wms-host-network.py "$DB_CONTAINER"
fi

# Keep assets referenced by already-open operator tabs. Preparation never starts
# the temporary container and finishes before any application writer is stopped.
WEB_ASSET_TMP=""
WEB_ASSET_CONTAINER=""
cleanup_web_assets() {
  local status=$?
  if [[ -n "$WEB_ASSET_CONTAINER" ]]; then
    docker rm "$WEB_ASSET_CONTAINER" >/dev/null 2>&1 || true
  fi
  if [[ -n "$WEB_ASSET_TMP" ]]; then rm -rf -- "$WEB_ASSET_TMP"; fi
  return "$status"
}
trap cleanup_web_assets EXIT

BUILD_SERVICES=(migrations api celery_worker celery_beat web)

echo "==> docker compose prod build (sequential)"
for service in "${BUILD_SERVICES[@]}"; do
  if [[ "$service" == "web" ]]; then
    WEB_PREVIOUS_CONTAINER="$("${COMPOSE[@]}" ps -q web)"
    if [[ -n "$WEB_PREVIOUS_CONTAINER" ]]; then
      # Resolve the build output from this exact compose configuration, never
      # from the old running container (which may use a different image tag).
      WEB_COMPOSE_IMAGES="$("${COMPOSE[@]}" config --images web)"
      WEB_IMAGE_TAG="$("${COMPOSE[@]}" config --format json web | \
        python3 scripts/deploy/retain-web-assets.py image-tag --declared-images "$WEB_COMPOSE_IMAGES")"
      WEB_ASSET_TMP="$(mktemp -d "${TMPDIR:-/tmp}/wms-web-assets.XXXXXX")"
      mkdir "$WEB_ASSET_TMP/previous"
      docker cp "$WEB_PREVIOUS_CONTAINER:/srv/." "$WEB_ASSET_TMP/previous/"
    fi
  fi
  "${COMPOSE[@]}" build "$service"
done

if [[ -n "$WEB_ASSET_TMP" ]]; then
  echo "==> retain previous assets in the new web image before traffic"
  WEB_NEW_IMAGE="$(docker image inspect --format '{{.Id}}' "$WEB_IMAGE_TAG")"
  WEB_ASSET_CONTAINER="$(docker create "$WEB_NEW_IMAGE")"
  mkdir "$WEB_ASSET_TMP/candidate" "$WEB_ASSET_TMP/verified"
  docker cp "$WEB_ASSET_CONTAINER:/srv/." "$WEB_ASSET_TMP/candidate/"
  WEB_ADDED_ASSETS="$(python3 scripts/deploy/retain-web-assets.py prepare \
    --previous "$WEB_ASSET_TMP/previous" --candidate "$WEB_ASSET_TMP/candidate" \
    --delta "$WEB_ASSET_TMP/delta" --manifest "$WEB_ASSET_TMP/manifest.json")"
  if [[ "$WEB_ADDED_ASSETS" != "0" ]]; then
    docker cp "$WEB_ASSET_TMP/delta/." "$WEB_ASSET_CONTAINER:/srv/"
  fi
  docker cp "$WEB_ASSET_CONTAINER:/srv/." "$WEB_ASSET_TMP/verified/"
  python3 scripts/deploy/retain-web-assets.py verify \
    --candidate "$WEB_ASSET_TMP/verified" --manifest "$WEB_ASSET_TMP/manifest.json"
  # Commit only verified extra old files; all freshly built assets stay identical.
  if [[ "$WEB_ADDED_ASSETS" != "0" ]]; then
    docker commit "$WEB_ASSET_CONTAINER" "$WEB_IMAGE_TAG" >/dev/null
  fi
  docker rm "$WEB_ASSET_CONTAINER" >/dev/null
  WEB_ASSET_CONTAINER=""
  rm -rf -- "$WEB_ASSET_TMP"
  WEB_ASSET_TMP=""
fi

echo "==> start infrastructure"
"${COMPOSE[@]}" up -d --wait db redis

# WMS-338 removes a retired table/column. Old writers must be stopped before
# applying schema changes, and the pre-migration database must be recoverable.
echo "==> stop application writers before schema migration"
"${COMPOSE[@]}" stop api celery_worker celery_beat

BACKUP_DIR="${WMS_BACKUP_DIR:-$(dirname "$REPO_DIR")/wms-backups}"
install -d -m 700 "$BACKUP_DIR"
BACKUP_FILE="${BACKUP_DIR}/pre-migration-$(date -u +%Y%m%dT%H%M%SZ)-${DEPLOY_SHA:0:12}.dump"
umask 077
echo "==> save private pre-migration PostgreSQL backup"
if ! "${COMPOSE[@]}" exec -T db sh -c \
  'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' </dev/null > "$BACKUP_FILE"; then
  echo "ERROR: backup failed; application writers remain stopped. No migration was run." >&2
  exit 1
fi
if [[ ! -s "$BACKUP_FILE" ]] || ! "${COMPOSE[@]}" exec -T db pg_restore --list \
  < "$BACKUP_FILE" > /dev/null; then
  echo "ERROR: backup archive is invalid; writers remain stopped. No migration was run." >&2
  exit 1
fi
echo "    backup archive saved and validated (contents are private)."

echo "==> run database migrations"
"${COMPOSE[@]}" run --rm migrations

echo "==> start application services"
"${COMPOSE[@]}" up -d --no-deps api celery_worker celery_beat web

# Read only non-secret settings from the running API, never its environment dump.
echo "==> verify public access settings"
"${COMPOSE[@]}" exec -T api python -c '
from app.core.settings import settings
assert settings.app_env == "production", "API must run in production mode"
assert not settings.allow_public_registration, "Public registration must be disabled"
assert settings.access_token_expire_minutes == 1440, "Access token TTL must be 24 hours"
print("production mode; public registration disabled; access token TTL 1440 minutes")
'

# The old separate seller container is no longer defined in production compose.
# Close only that project's obsolete HTTP listener after the combined web serves
# its seller route; do not remove unrelated services or touch the outer Caddy.
if [[ -f docker-compose.wms-host-8088.yml ]]; then
  echo "==> verify seller route before closing legacy listener"
  curl --fail --silent --show-error --retry 10 --retry-connrefused --retry-delay 3 \
    --max-time 15 http://172.18.0.1:8088/seller/ > /dev/null
  DB_CONTAINER="$("${COMPOSE[@]}" ps -q db)"
  PROJECT_NAME="$(docker inspect "$DB_CONTAINER" \
    --format '{{index .Config.Labels "com.docker.compose.project"}}')"
  if [[ -z "$PROJECT_NAME" ]]; then
    echo "ERROR: unable to establish compose project for legacy listener." >&2
    exit 1
  fi
  LEGACY_CONTAINERS="$(docker ps -q --filter "label=com.docker.compose.project=$PROJECT_NAME" \
    --filter 'label=com.docker.compose.service=web_seller')"
  while IFS= read -r container_id; do
    if [[ -n "$container_id" ]]; then
      docker stop "$container_id"
    fi
  done <<< "$LEGACY_CONTAINERS"
fi

echo "==> status"
"${COMPOSE[@]}" ps

# Переимпорт карточек WB из выкатки убран 29.08.2026.
#
# Он появился 14.06.2026 вместе с разовой перестройкой каталога (один товар на
# размер, старые артикулы в OLD/…) и с тех пор гонялся после КАЖДОЙ выкатки:
# массовая перезапись 12490 боевых товаров по 34 продавцам без подтверждения.
# Задачу свою он выполнил тогда же, карточки и так подтягивает фоновая
# синхронизация, а падения по нехватке памяти (код 137) стали привычными.
#
# Нужен разово — запускать руками и под наблюдением:
#   ./scripts/deploy/sync-all-wb-products.sh

echo "Done. Check https://${WMS_PUBLIC_DOMAIN:-your-domain}"
