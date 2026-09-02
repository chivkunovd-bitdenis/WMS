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
