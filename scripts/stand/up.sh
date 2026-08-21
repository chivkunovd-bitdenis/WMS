#!/usr/bin/env bash
# Поднять полосу стенда и отдать готовые креды. Агент стенд не поднимает и не ищет —
# он получает адрес и пароль в промпте. Не открылось — падает честно, а не идёт искать.
#
#   ./scripts/stand/up.sh 1          поднять полосу 1
#   ./scripts/stand/up.sh 1 --креды  только напечатать креды, ничего не поднимая
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
LANE="${1:?нужен номер полосы: 1..6}"
[[ "$LANE" =~ ^[1-6]$ ]] || { echo "полоса может быть от 1 до 6" >&2; exit 2; }

# Порты разведены по полосам, чтобы три стека жили одновременно и не мешали
# уже поднятому e2e-стенду в 28xxx.
export WMS_API_PORT="3008$LANE"
export WMS_WEB_PORT="3017$LANE"
export WMS_SELLER_WEB_PORT="3018$LANE"
export WMS_DB_PORT="3043$LANE"
export WMS_REDIS_PORT="3037$LANE"
PROJECT="wms-lane-$LANE"
PASS="${WMS_STAND_PASSWORD:-Стенд123}"
URL="http://localhost:$WMS_WEB_PORT"

креды() {
  local mail
  mail="$(docker exec "$PROJECT-db-1" psql -U postgres -d wms -t -A -c \
    "select coalesce(
  -- Пользователь того тенанта, где заказов больше всего: кликеру нужен экран с данными,
  -- а не пустой. Приложение при старте заводит собственного тестового админа в отдельном
  -- тенанте — залогинившись им, агент видит пустые списки и пишет, что всё в порядке.
  (select u.email from users u
     join (select tenant_id, count(*) n from fbs_orders group by tenant_id
           order by n desc limit 1) t on t.tenant_id = u.tenant_id
    where u.seller_id is null order by u.created_at limit 1),
  (select email from users where seller_id is null order by created_at limit 1))" 2>/dev/null || true)"
  echo "СТЕНД ПОЛОСЫ $LANE"
  echo "  адрес:  $URL"
  echo "  логин:  ${mail:-НЕ НАЙДЕН}"
  echo "  пароль: $PASS"
  echo "  API:    http://localhost:$WMS_API_PORT"
  if [[ "${WB_GUARD_ALLOW_WRITES:-0}" == "1" ]]; then
    echo "  WB:     ЗАПИСЬ В ЖИВОЙ КАБИНЕТ РАЗРЕШЕНА ВЛАДЕЛЬЦЕМ"
  else
    echo "  WB:     живой кабинет Denmarcs, только чтение (запись режет wb-guard)"
  fi
}

if [[ "${2:-}" == "--креды" ]]; then креды; exit 0; fi

# Без эмулятора: владелец разрешил тестировать на своём кабинете Denmarcs, и его ключ
# в снимке оставлен живым намеренно. Остальные 26 ключей вычищены — чужие кабинеты
# недостижимы в принципе, потому что токенов для них в базе нет.
# docker-compose.lane.yml ставит сторожа перед живым кабинетом WB: читать можно всё,
# писать нельзя. Владелец разрешил тестировать на своём кабинете Denmarcs, но кнопка
# «Передать в WB» означает настоящую отгрузку, а оприходованные остатки — обещание
# маркетплейсу товара, которого нет.
COMPOSE=(docker compose -p "$PROJECT" -f "$ROOT/docker-compose.yml" -f "$ROOT/docker-compose.lane.yml")

# Полосы переиспользуют уже собранные образы вместо своей сборки. Имя проекта у каждой
# полосы своё, поэтому compose по умолчанию строит ей отдельные образы — девять карточек
# дают девять сборок одного и того же кода по пятнадцать минут, и ночь умирает на этом.
# Берём образы первой полосы и подставляем их под имя своей.
for SVC in api celery_worker web; do
  SRC="wms-lane-1-${SVC}:latest"
  DST="${PROJECT}-${SVC}:latest"
  if [[ "$LANE" != "1" ]] && docker image inspect "$SRC" >/dev/null 2>&1 \
     && ! docker image inspect "$DST" >/dev/null 2>&1; then
    docker tag "$SRC" "$DST" && echo "    образ $SVC взят у полосы 1, сборка не нужна"
  fi
done

echo "1/4 поднимаю стек полосы $LANE (порты 3xx$LANE)"
"${COMPOSE[@]}" up -d --wait db redis >/dev/null 2>&1
"${COMPOSE[@]}" up -d wb-guard >/dev/null 2>&1
"${COMPOSE[@]}" run --rm migrations >/dev/null 2>&1 || true
"${COMPOSE[@]}" up -d --no-deps api celery_worker web >/dev/null 2>&1

echo "2/4 жду, пока API ответит"
for i in $(seq 1 60); do
  if curl -sf -m 3 "http://localhost:$WMS_API_PORT/health" >/dev/null 2>&1; then break; fi
  [[ $i -eq 60 ]] && { echo "    API не поднялся за 60 секунд" >&2; "${COMPOSE[@]}" logs --tail 30 api >&2; exit 1; }
  sleep 1
done
echo "    API отвечает"

echo "3/4 разворачиваю боевой снимок"
# Гасим приложение на время подмены базы: пока api и celery подключены, DROP DATABASE
# не пройдёт. Поднимаем обратно здесь же — только у этого скрипта есть порты полосы.
"${COMPOSE[@]}" stop api celery_worker celery_beat >/dev/null 2>&1 || true
"$ROOT/scripts/stand/restore.sh" "$LANE"
"${COMPOSE[@]}" up -d --no-deps api celery_worker >/dev/null 2>&1
for i in $(seq 1 60); do
  curl -sf -m 3 "http://localhost:$WMS_API_PORT/health" >/dev/null 2>&1 && break
  [[ $i -eq 60 ]] && { echo "    API не вернулся на порт $WMS_API_PORT" >&2; exit 1; }
  sleep 1
done

echo "4/5 ставлю пароль стендовому админу"
# Хэш считает сам бэкенд своей же функцией — стенд не разойдётся с приложением, если
# алгоритм поменяют. Делается здесь, а не в restore.sh: там контейнер API ещё погашен.
HASH="$(docker exec "$PROJECT-api-1" python -c \
  "from app.services.passwords import hash_password; print(hash_password('$PASS'))" 2>/dev/null)"
[[ -n "$HASH" ]] || { echo "    не удалось посчитать хэш через api — кликер не войдёт" >&2; exit 1; }
MAIL="$(docker exec "$PROJECT-db-1" psql -U postgres -d wms -t -A -c \
  "select coalesce(
  -- Пользователь того тенанта, где заказов больше всего: кликеру нужен экран с данными,
  -- а не пустой. Приложение при старте заводит собственного тестового админа в отдельном
  -- тенанте — залогинившись им, агент видит пустые списки и пишет, что всё в порядке.
  (select u.email from users u
     join (select tenant_id, count(*) n from fbs_orders group by tenant_id
           order by n desc limit 1) t on t.tenant_id = u.tenant_id
    where u.seller_id is null order by u.created_at limit 1),
  (select email from users where seller_id is null order by created_at limit 1))")"
[[ -n "$MAIL" ]] || { echo "    в снимке нет ни одного пользователя ФФ" >&2; exit 1; }
docker exec "$PROJECT-db-1" psql -U postgres -d wms -q -c \
  "update users set password_hash='$HASH', must_set_password=false where email='$MAIL'"
echo "    вход готов"

echo "5/5 проверяю, что экран открывается"
HTTP_CODE="$(curl -s -o /dev/null -w '%{http_code}' -m 5 "$URL/" || echo 000)"
[[ "$HTTP_CODE" == "200" ]] || { echo "    фронт отдал $HTTP_CODE вместо 200" >&2; exit 1; }
echo "    фронт отвечает"
echo
креды
