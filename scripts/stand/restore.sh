#!/usr/bin/env bash
# Быстрая подмена базы полосы копией боевого снимка.
#
# Секрет скорости — шаблонная база. Снимок разворачивается один раз в `wms_snapshot`
# (это минуты), а дальше каждая полоса получает свою копию командой
# CREATE DATABASE wms TEMPLATE wms_snapshot — постгрес просто копирует файлы, это секунды.
# Разворачивать 375-мегабайтный дамп на каждую полосу и перед каждым сбросом — утопия:
# так один стенд обходился в три минуты, а их три, и сбрасывать их надо не по разу.
#
#   ./scripts/stand/restore.sh 1
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
LANE="${1:?нужен номер полосы: 1..6}"
READY="$ROOT/.stand/sanitized-latest.dump"
DB_C="wms-lane-$LANE-db-1"
TPL="wms_snapshot"

[[ -f "$READY" ]] || { echo "нет снимка $READY — сначала scripts/stand/snapshot.sh" >&2; exit 2; }

psql_() { docker exec "$DB_C" psql -U postgres -d postgres -q "$@"; }
есть_шаблон() {
  [[ "$(docker exec "$DB_C" psql -U postgres -d postgres -t -A \
        -c "select 1 from pg_database where datname='$TPL'" 2>/dev/null)" == "1" ]]
}

if ! есть_шаблон; then
  echo "    шаблона нет — разворачиваю снимок один раз (это минуты, дальше будут секунды)"
  python3 "$ROOT/scripts/ci/check_stand_sanitized.py" "$READY"
  psql_ -c "CREATE DATABASE $TPL"
  docker exec -i "$DB_C" pg_restore -U postgres -d "$TPL" --no-owner --no-acl < "$READY" 2>&1 \
    | grep -viE "warning|already exists" | head -3 || true
  # Шаблон помечаем неизменяемым, чтобы никто в него случайно не написал:
  # все полосы копируются из него, и порча шаблона портит всю ночь разом.
  psql_ -c "ALTER DATABASE $TPL IS_TEMPLATE true" >/dev/null 2>&1 || true
fi

# Рвём соединения и делаем копию. Обе команды быстрые.
psql_ -c "select pg_terminate_backend(pid) from pg_stat_activity where datname in ('wms','$TPL') and pid <> pg_backend_pid()" >/dev/null 2>&1 || true
psql_ -c "DROP DATABASE IF EXISTS wms"
psql_ -c "CREATE DATABASE wms TEMPLATE $TPL"

# Отсутствие ошибки — не доказательство: pg_restore охотно завершается с нулём на пустой
# базе, и кликер потом всю ночь ходит по стенду без единого заказа.
N_SELLERS="$(docker exec "$DB_C" psql -U postgres -d wms -t -A -c 'select count(*) from sellers' 2>/dev/null || echo 0)"
N_ORDERS="$(docker exec "$DB_C" psql -U postgres -d wms -t -A -c 'select count(*) from fbs_orders' 2>/dev/null || echo 0)"
[[ "$N_SELLERS" -ge 1 && "$N_ORDERS" -ge 1 ]] || {
  echo "    снимок не лёг: селлеров $N_SELLERS, заказов FBS $N_ORDERS" >&2; exit 1; }
echo "    база полосы $LANE: селлеров $N_SELLERS, заказов FBS $N_ORDERS"
