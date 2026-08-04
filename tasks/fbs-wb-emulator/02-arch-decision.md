# 02 — Арх-решение + стек  🔒 ГЕЙТ 1

> Заполняет: агент, затем **человек ставит явное «ок»**. Без подтверждения человека — КОД ПИСАТЬ НЕЛЬЗЯ.
> Это же — запись в живую арх-карту (`.dev/ARCHITECTURE.md`, раздел «Подтверждённые решения»).

## Принятое решение

- **Подход:** Standalone HTTP-сервис **wb-emulator**, который прикидывается WB Marketplace API v3 (`/api/v3/...`). WMS переключается на него **одной переменной окружения** `WILDBERRIES_MARKETPLACE_API_BASE` → `settings.wildberries_marketplace_api_base` (уже есть в `backend/app/core/settings.py`, дефолт `https://marketplace-api.wildberries.ru`). Клиент `wildberries_client.py` строит все Marketplace-URL как `{base}{MARKETPLACE_*_PATH}` — эмулятор зеркалит контракт клиента 1:1, источник правды по полям ответа — тот же файл + сервисы FBS. Админ-ручки эмулятора (`/__admin/...`) — только для тестовой среды, не часть WB API.

- **Стек / инструменты:**
  - Python 3.11+, FastAPI, uvicorn
  - SQLite (файл на Docker volume; состояние переживает рестарт)
  - `python-barcode` + `qrcode` или `segno` — реальные PNG стикеров (Code128 58×40, QR поставки/грузоместа)
  - Пакет в корне репо: `wb_emulator/` (НЕ внутри `backend/app/`)
  - Сид заказов: фикстуры `wb_emulator/seed/<seller>.json` (баркоды/nmId из реального каталога селлера)
  - Тесты: pytest в пакете эмулятора (контракт ответов = как читает `wildberries_client.py`); интеграция — полный FBS-цикл против эмулятора с env override
  - Docker: сервис `wb-emulator` в **отдельном** compose-файле (см. `compose-survey.md`)

- **Затрагиваемые части системы:**
  - **Новые:** `wb_emulator/**` (приложение, модели SQLite, роуты `/api/v3/*` и `/__admin/*`, seed, Dockerfile)
  - **Новые:** `docker-compose.emulator.yml` (или аналогичный test-only override) — сервис `wb-emulator` + env `WILDBERRIES_MARKETPLACE_API_BASE=http://wb-emulator:8000` на `api`, `celery_worker`, `celery_beat`
  - **НЕ трогаем:** `backend/app/**` (код WMS), `docker-compose.prod.yml`
  - **Уже есть (документируем, не меняем):** `backend/app/core/settings.py` — поле `wildberries_marketplace_api_base` (env `WILDBERRIES_MARKETPLACE_API_BASE`); `backend/app/services/wildberries_client.py` — все Marketplace-вызовы через `settings.wildberries_marketplace_api_base`
  - **Документация:** `tasks/fbs-wb-emulator/*`, при merge — блок в `.dev/ARCHITECTURE.md`

- **Осознанно НЕ делаем:**
  - Моки/ветки `e2e_mock_wb_marketplace_*` внутри WMS-сервисов для замены эмулятора — дублируют контракт и не дают полного HTTP-цикла
  - Изменения `wildberries_client.py` или FBS-сервисов «для эмулятора» — нарушает принцип «одна env, тот же код»
  - Подключение эмулятора в `docker-compose.prod.yml` или prod env — прод всегда бьёт в реальный WB
  - Эмулятор внутри `backend/app` — отдельный deployable unit, свой lifecycle и volume
  - Alembic-миграции WMS — эмулятор не трогает PostgreSQL WMS
  - **`GET /api/v3/supplies/{id}` (+ `/orders`) из TASK.md** — в `wildberries_client.py` **не вызываются** (`contract-from-client.md`); v1 не обязателен. Если удобно для `/__admin/state` — можно stub, но не DoD.

- **Влияние на прод/данные/миграции:**
  - **Миграции WMS DB:** нет
  - **Прод:** без изменений; `docker-compose.prod.yml` не содержает `wb-emulator` и `WILDBERRIES_MARKETPLACE_API_BASE` (проверено в `compose-survey.md`)
  - **Тест/staging:** opt-in через второй compose-файл; локально — `docker compose -f docker-compose.yml -f docker-compose.emulator.yml up`

## Стыковка (кратко)

| Компонент | Как WMS узнаёт эмулятор |
|-----------|-------------------------|
| api | `WILDBERRIES_MARKETPLACE_API_BASE=http://wb-emulator:8000` (test compose only) |
| celery_worker | то же (автопрос, статусы, отгрузки) |
| celery_beat | то же (beat триггерит задачи, worker делает HTTP) |
| wb-emulator | порт 8000 внутри сети compose; volume для SQLite + mount `seed/` |

Мультиселлер: WMS шлёт `Authorization: <token>`; эмулятор мапит токен → seller_key (env/конфиг); неизвестный токен → 401.

## 🔒 Подтверждение человека (ГЕЙТ 1)

- **Статус:** ✅ подтверждено
- **Кто и когда:** владелец, 2026-08-02
- **Комментарий/правки человека:** «как в ТЗ — так и сделай» (= Agent/A: standalone `wb_emulator/`, одна env, override compose, код WMS не трогаем)

> ГЕЙТ 1 пройден — код разрешён.
