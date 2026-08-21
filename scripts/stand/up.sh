#!/usr/bin/env bash
# Поднять полосу стенда и отдать готовые креды. Агент стенд не поднимает и не ищет —
# он получает адрес и пароль в промпте. Не открылось — падает честно, а не идёт искать.
#
#   ./scripts/stand/up.sh 1          поднять полосу 1
#   ./scripts/stand/up.sh 1 --креды  только напечатать креды, ничего не поднимая
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
LANE="${1:?нужен номер полосы: 1, 2 или 3}"
[[ "$LANE" =~ ^[1-3]$ ]] || { echo "полоса может быть 1, 2 или 3" >&2; exit 2; }

# Порты разведены по полосам, чтобы три стека жили одновременно и не мешали
# уже поднятому e2e-стенду в 28xxx.
export WMS_API_PORT="3008$LANE"
export WMS_WEB_PORT="3017$LANE"
export WMS_SELLER_WEB_PORT="3018$LANE"
export WMS_DB_PORT="3043$LANE"
export WMS_REDIS_PORT="3037$LANE"
export WB_EMULATOR_PORT="3028$LANE"
export WB_EMULATOR_ADMIN_TOKEN="${WB_EMULATOR_ADMIN_TOKEN:-fbs-e2e-admin}"
PROJECT="wms-lane-$LANE"
PASS="${WMS_STAND_PASSWORD:-Стенд123}"
URL="http://localhost:$WMS_WEB_PORT"

креды() {
  local mail
  mail="$(docker exec "$PROJECT-db-1" psql -U postgres -d wms -t -A -c \
    "select email from users where seller_id is null order by created_at limit 1" 2>/dev/null || true)"
  echo "СТЕНД ПОЛОСЫ $LANE"
  echo "  адрес:  $URL"
  echo "  логин:  ${mail:-НЕ НАЙДЕН}"
  echo "  пароль: $PASS"
  echo "  API:    http://localhost:$WMS_API_PORT"
}

if [[ "${2:-}" == "--креды" ]]; then креды; exit 0; fi

COMPOSE=(docker compose -p "$PROJECT" -f "$ROOT/docker-compose.yml" -f "$ROOT/docker-compose.emulator.yml")

echo "1/4 поднимаю стек полосы $LANE (порты 3xx$LANE)"
"${COMPOSE[@]}" up -d --wait db redis >/dev/null 2>&1
"${COMPOSE[@]}" run --rm migrations >/dev/null 2>&1 || true
"${COMPOSE[@]}" up -d --no-deps api celery_worker web wb-emulator >/dev/null 2>&1

echo "2/4 жду, пока API ответит"
for i in $(seq 1 60); do
  if curl -sf -m 3 "http://localhost:$WMS_API_PORT/health" >/dev/null 2>&1; then break; fi
  [[ $i -eq 60 ]] && { echo "    API не поднялся за 60 секунд" >&2; "${COMPOSE[@]}" logs --tail 30 api >&2; exit 1; }
  sleep 1
done
echo "    API отвечает"

echo "3/4 разворачиваю боевой снимок"
WMS_STAND_DB_PREFIX="wms-lane" WMS_STAND_API_PREFIX="wms-lane" \
  "$ROOT/scripts/stand/restore.sh" "$LANE"

echo "4/4 проверяю, что экран открывается"
код="$(curl -s -o /dev/null -w '%{http_code}' -m 5 "$URL/" || echo 000)"
[[ "$код" == "200" ]] || { echo "    фронт отдал $код вместо 200" >&2; exit 1; }
echo "    фронт отвечает"
echo
креды
