#!/usr/bin/env bash
# Свежий снимок боевой базы для стенда: снять, обезличить, проверить, положить файлом.
#
# Зачем боевой снимок, а не сид: каждый крит, найденный 21.08, живёт только в форме реальных
# данных. Одиннадцать номеров WB с двумя карточками поставки, девять селлеров с битым токеном,
# товар в ячейке одного склада при задании на другом, 5677 заказов из 8776 без права на ПВЗ —
# ничего из этого синтетический сид не воспроизведёт, потому что его автор об этом не знал.
#
# Направление одно: прод -> стенд. Обратной операции здесь нет и быть не должно.
#
#   ./scripts/stand/snapshot.sh                     снять свежий
#   ./scripts/stand/snapshot.sh --только-проверить  проверить последний готовый
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
STORE="$ROOT/.stand"
LIVE_SELLER="${WMS_STAND_LIVE_SELLER:-080f5f98-195e-49b5-9dd5-908dbc862a13}"   # Denmarcs
PROD_SSH="${WMS_PROD_SSH:-root@194.87.96.144}"
PROD_DB="${WMS_PROD_DB_CONTAINER:-wms_prod-db-1}"
SCRATCH="${WMS_STAND_SCRATCH_DB:-wms-honest-e2e-db-1}"
TMPDB="stand_scratch"

mkdir -p "$STORE"
READY="$STORE/sanitized-latest.dump"

if [[ "${1:-}" == "--только-проверить" ]]; then
  exec python3 "$ROOT/scripts/ci/check_stand_sanitized.py" "$READY"
fi

RAW="$STORE/raw-$(date +%Y%m%d-%H%M).dump"
# Сырой дамп живёт минуты и удаляется в любом случае, даже если обезличивание упало:
# боевым ключам нечего делать на ноутбуке.
trap 'rm -f "$RAW"' EXIT

echo "1/5 снимаю боевую базу (только чтение)"
ssh -o BatchMode=yes "$PROD_SSH" "docker exec $PROD_DB pg_dump -U postgres -d wms -Fc" > "$RAW"
echo "    снято: $(du -h "$RAW" | cut -f1)"

echo "2/5 разворачиваю во временную базу"
docker exec "$SCRATCH" psql -U postgres -q -c "DROP DATABASE IF EXISTS $TMPDB" >/dev/null
docker exec "$SCRATCH" psql -U postgres -q -c "CREATE DATABASE $TMPDB" >/dev/null
docker exec -i "$SCRATCH" pg_restore -U postgres -d "$TMPDB" --no-owner --no-acl < "$RAW" 2>&1 \
  | grep -viE "warning|already exists" | head -5 || true

echo "3/5 обезличиваю"
docker exec -i "$SCRATCH" psql -U postgres -d "$TMPDB" -v живой_селлер="$LIVE_SELLER" -q \
  < "$ROOT/scripts/stand/sanitize.sql" | sed 's/^/    /'

echo "4/5 складываю обезличенный снимок"
docker exec "$SCRATCH" pg_dump -U postgres -d "$TMPDB" -Fc > "$READY"
docker exec "$SCRATCH" psql -U postgres -q -c "DROP DATABASE $TMPDB" >/dev/null
echo "    готово: $READY ($(du -h "$READY" | cut -f1))"

echo "5/5 сторож: не уцелел ли живой ключ"
python3 "$ROOT/scripts/ci/check_stand_sanitized.py" "$READY"
