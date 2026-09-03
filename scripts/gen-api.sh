#!/usr/bin/env bash
# Регенерация Kotlin API-клиента из OpenAPI-схемы бэкенда.
# Использование: mobile/scripts/gen-api.sh
# Схема берётся с запущенного бэкенда (localhost:8000), иначе дампится из кода
# через backend/.venv. Результат: mobile/android/app/src/main/java/ru/wms/tsd/core/api/generated/
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SPEC="$ROOT/mobile/openapi.json"
# ВАЖНО: путь проекта содержит пробел ("WMS "), а npm-обёртка openapi-generator-cli
# ломает аргументы с пробелами. Поэтому генерируем во временной папке без пробелов.
WORK_DIR="/tmp/wms-api-gen"
OUT_DIR="$WORK_DIR/out"
TARGET_PKG="ru.wms.tsd.core.api.generated"
APP_SRC="$ROOT/mobile/android/app/src/main/java"

echo "== Получение openapi.json =="
# Порядок: docker compose (:18080) → dev-uvicorn (:8000, ОСТОРОЖНО: там может жить
# другой проект — проверяем title) → дамп из кода. Инцидент 06.07: на :8000 был
# чужой бэкенд, клиент сгенерировался от чужой схемы.
fetch_spec() {
  curl -sf "http://localhost:$1/openapi.json" -o "$SPEC" || return 1
  python3 -c "import json,sys; sys.exit(0 if json.load(open('$SPEC'))['info']['title']=='WMS API' else 1)" || return 1
}
if fetch_spec 18080; then
  echo "  взят с docker-бэкенда :18080"
elif fetch_spec 8000; then
  echo "  взят с dev-бэкенда :8000"
else
  echo "  бэкенд не запущен, дампим из кода"
  (cd "$ROOT/backend" && DATABASE_URL="sqlite+aiosqlite:///:memory:" .venv/bin/python -c "
import json
from app.main import app
with open('$SPEC', 'w') as f:
    json.dump(app.openapi(), f, ensure_ascii=False, indent=1)
print('  paths:', len(app.openapi()['paths']))
")
fi

echo "== Генерация Kotlin-клиента =="
rm -rf "$WORK_DIR"
mkdir -p "$WORK_DIR"
cp "$SPEC" "$WORK_DIR/openapi.json"
npx --yes @openapitools/openapi-generator-cli generate \
  -i "$WORK_DIR/openapi.json" \
  -g kotlin \
  -o "$OUT_DIR" \
  --library jvm-retrofit2 \
  --additional-properties=useCoroutines=true,serializationLibrary=kotlinx_serialization,packageName=$TARGET_PKG,omitGradleWrapper=true \
  --type-mappings=AnyType=kotlinx.serialization.json.JsonElement \
  --import-mappings=kotlinx.serialization.json.JsonElement=kotlinx.serialization.json.JsonElement

echo "== Копирование в проект =="
DEST="$APP_SRC/ru/wms/tsd/core/api/generated"
rm -rf "$DEST"
mkdir -p "$(dirname "$DEST")"
cp -R "$OUT_DIR/src/main/kotlin/ru/wms/tsd/core/api/generated" "$DEST"
echo "OK: $DEST"
