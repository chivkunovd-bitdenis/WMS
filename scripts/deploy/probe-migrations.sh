#!/usr/bin/env bash
# Репетиция накатки миграций на КОПИИ боевой базы. Рабочую базу не трогает.
#
# Запускать НА БОЕВОМ СЕРВЕРЕ из /opt/wms. Делает три вещи:
#   1) снимает копию базы wms в отдельную базу wms_probe;
#   2) собирает образ миграций из указанной ветки во временном worktree;
#   3) прогоняет alembic upgrade head на копии с замером времени.
#
# Смысл: тесты гоняются на sqlite, поэтому постгресовые куски миграций —
# триггеры, btree_gist, ограничения EXCLUDE — не проверялись нигде. Плюс даёт
# честную цифру: сколько длится окно, когда старый код работает поверх новой схемы.
set -euo pipefail

BRANCH="${1:?укажи ветку, например integration/vse-v-etalon-20260828}"
PROBE_DB="${PROBE_DB:-wms_probe}"
WORK="/tmp/wms-probe-$$"
COMPOSE=(docker compose -f docker-compose.prod.yml)

cleanup() {
  echo "==> уборка"
  git -C /opt/wms worktree remove --force "$WORK" 2>/dev/null || true
  "${COMPOSE[@]}" exec -T db psql -U postgres -d postgres \
    -c "DROP DATABASE IF EXISTS ${PROBE_DB}" >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "==> копия базы в ${PROBE_DB}"
"${COMPOSE[@]}" exec -T db psql -U postgres -d postgres -c "DROP DATABASE IF EXISTS ${PROBE_DB}" >/dev/null
"${COMPOSE[@]}" exec -T db psql -U postgres -d postgres -c "CREATE DATABASE ${PROBE_DB}" >/dev/null
"${COMPOSE[@]}" exec -T db sh -c "pg_dump -U postgres -d wms | psql -q -U postgres -d ${PROBE_DB}" >/dev/null
echo "    ревизия в копии: $("${COMPOSE[@]}" exec -T db psql -U postgres -d "${PROBE_DB}" -tAc 'select version_num from alembic_version')"
echo "    отрицательных остатков в копии: $("${COMPOSE[@]}" exec -T db psql -U postgres -d "${PROBE_DB}" -tAc 'select count(*) from inventory_balances where quantity < 0 or quantity_unpacked < 0 or quantity_packed < 0')"

echo "==> временный worktree на ${BRANCH}"
git -C /opt/wms fetch --quiet origin "${BRANCH}"
git -C /opt/wms worktree add --detach "$WORK" FETCH_HEAD >/dev/null 2>&1
echo "    коммит: $(git -C "$WORK" log -1 --format='%h %s')"

echo "==> сборка образа миграций"
# .env лежит только в боевой папке — временный worktree берёт переменные оттуда.
( cd "$WORK" && docker compose --env-file /opt/wms/.env -f docker-compose.prod.yml build migrations >/dev/null )

echo "==> НАКАТКА (замер времени)"
DB_URL="postgresql+psycopg://postgres:$(grep -E '^POSTGRES_PASSWORD=' /opt/wms/.env | cut -d= -f2-)@db:5432/${PROBE_DB}"
START=$(date +%s)
( cd "$WORK" && docker compose --env-file /opt/wms/.env -f docker-compose.prod.yml run --rm \
    -e DATABASE_URL="$DB_URL" migrations )
END=$(date +%s)

echo
echo "======================================"
echo "  НАКАТКА ПРОШЛА ЗА $((END-START)) СЕКУНД"
echo "======================================"
echo "    ревизия после: $("${COMPOSE[@]}" exec -T db psql -U postgres -d "${PROBE_DB}" -tAc 'select version_num from alembic_version')"
