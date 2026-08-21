#!/usr/bin/env bash
# Развернуть обезличенный снимок в базу одной полосы стенда.
#
# Все полосы одной ночи обязаны стоять на ОДНОМ снимке: иначе задача в первой полосе и
# задача в третьей видят разные данные, находки становятся невоспроизводимыми, и утром
# не разобрать, кто прав.
#
#   ./scripts/stand/restore.sh 1        # полоса 1
#   ./scripts/stand/restore.sh 2 --пароль Стенд123
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
LANE="${1:?нужен номер полосы: 1, 2 или 3}"
PASS="${WMS_STAND_PASSWORD:-Стенд123}"
READY="$ROOT/.stand/sanitized-latest.dump"
DB_C="${WMS_STAND_DB_PREFIX:-wms-lane}-$LANE-db-1"
API_C="${WMS_STAND_API_PREFIX:-wms-lane}-$LANE-api-1"

[[ -f "$READY" ]] || { echo "нет снимка $READY — сначала scripts/stand/snapshot.sh" >&2; exit 2; }

echo "1/3 сторож: снимок обезличен?"
python3 "$ROOT/scripts/ci/check_stand_sanitized.py" "$READY"

echo "2/3 разворачиваю в полосу $LANE"
docker exec "$DB_C" psql -U postgres -q -c "DROP DATABASE IF EXISTS wms" >/dev/null
docker exec "$DB_C" psql -U postgres -q -c "CREATE DATABASE wms" >/dev/null
docker exec -i "$DB_C" pg_restore -U postgres -d wms --no-owner --no-acl < "$READY" 2>&1 \
  | grep -viE "warning|already exists" | head -5 || true

echo "3/3 ставлю пароль стендовому админу"
# Хэш считает сам бэкенд своей же функцией — так стенд не расходится с приложением,
# если алгоритм когда-нибудь поменяют.
HASH="$(docker exec "$API_C" python -c \
  "from app.services.passwords import hash_password; print(hash_password('$PASS'))" 2>/dev/null)"
if [[ -z "$HASH" ]]; then
  echo "    не удалось посчитать хэш через api — кликер не сможет войти" >&2
  exit 1
fi
MAIL="$(docker exec "$DB_C" psql -U postgres -d wms -t -A -c \
  "select email from users where seller_id is null order by created_at limit 1")"
docker exec "$DB_C" psql -U postgres -d wms -q -c \
  "update users set password_hash='$HASH', must_set_password=false where email='$MAIL'"
echo "    вход на полосу $LANE: $MAIL / $PASS"
