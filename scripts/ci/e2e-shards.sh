#!/bin/bash
# Параллельный запуск браузерных сценариев несколькими независимыми копиями.
#
# Зачем. В playwright.config.ts стоит workers: 1, и это правильно: все сценарии
# ходят в один поднятый сервер API и один файл базы, а при нескольких потоках
# база блокируется и тесты начинают врать. Поэтому параллелим не потоки внутри
# одного прогона, а сами прогоны: каждая копия получает свой порт API, свой
# веб-сервер и свой файл базы, и берёт свою долю сценариев через --shard.
#
# Настройки менять не требуется: порты и файл базы уже читаются из переменных
# E2E_API_PORT, E2E_WEB_PORT и E2E_DB_FILE. Файлы вида backend/e2e-*.db лежат
# в .gitignore.
#
# Использование:
#   scripts/ci/e2e-shards.sh [число_копий]        # по умолчанию 4
#
# Пример: scripts/ci/e2e-shards.sh 4
set -u

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT/frontend" || exit 1

N=${1:-4}
if ! [[ "$N" =~ ^[0-9]+$ ]] || [ "$N" -lt 1 ]; then
  echo "Число копий должно быть целым и не меньше единицы, получено: $N" >&2
  exit 2
fi

LOG_DIR="${E2E_SHARD_LOG_DIR:-/tmp/wms-e2e-shards}"
mkdir -p "$LOG_DIR"

echo "Запускаю $N параллельных копий браузерных сценариев."
echo "Логи: $LOG_DIR/shard-<N>.log"
echo

START=$(date +%s)
pids=()
for i in $(seq 1 "$N"); do
  E2E_API_PORT=$((18000 + i)) \
  E2E_WEB_PORT=$((5180 + i)) \
  E2E_DB_FILE="e2e-$i.db" \
  npx playwright test --shard="$i/$N" --reporter=line \
    > "$LOG_DIR/shard-$i.log" 2>&1 &
  pids+=($!)
done

failed=0
for idx in "${!pids[@]}"; do
  if ! wait "${pids[$idx]}"; then
    failed=$((failed + 1))
  fi
done
END=$(date +%s)

echo "=== Результат ==="
for i in $(seq 1 "$N"); do
  line=$(grep -Eo '[0-9]+ (passed|failed|flaky)[^)]*' "$LOG_DIR/shard-$i.log" | tail -1)
  printf "  копия %-2s %s\n" "$i" "${line:-нет итоговой строки, смотри лог}"
done
echo
echo "Общее время: $((END - START)) секунд"

if [ "$failed" -gt 0 ]; then
  echo "Копий с ошибкой: $failed. Прогон считается красным."
  exit 1
fi
echo "Все копии зелёные."
