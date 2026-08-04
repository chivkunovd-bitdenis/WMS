# 06 — Документация — fbs-wb-emulator

## Зачем
Отдельный HTTP-сервис прикидывается WB Marketplace API v3. WMS на тесте бьёт в него одной переменной `WILDBERRIES_MARKETPLACE_API_BASE` — код WMS не меняется.

## Как поднять (локально / стенд)

```bash
docker compose -f docker-compose.yml -f docker-compose.emulator.yml up -d --build
```

- Эмулятор: порт `${WB_EMULATOR_PORT:-18081}` → внутри `8000`
- `api` / `celery_worker` / `celery_beat` получают `WILDBERRIES_MARKETPLACE_API_BASE=http://wb-emulator:8000`
- SQLite: volume `wb_emulator_data`
- Токены / admin: см. `wb_emulator/.env.example` и `wb_emulator/README.md`

**Прод:** `docker-compose.prod.yml` эмулятор не содержит — туда не добавлять.

## Кнопка «упал заказ»

```http
POST /__admin/orders?seller=seller_a&count=3
X-Admin-Token: <WB_EMULATOR_ADMIN_TOKEN>
```

Дальше автопрос WMS тянет `GET /api/v3/orders/new` с токеном селлера.

## Проверка контракта

```bash
cd "/Users/deniscivkunov/Desktop/WMS "
PYTHONPATH=. python3 -m pytest wb_emulator/tests/ -q
```

Кейсы: `tasks/fbs-wb-emulator/04-test-cases.md` (TC-NEW-FBS-EMU-001…003).

## Ссылки
- ТЗ: `tasks/fbs-wb-emulator/TASK.md`
- Контракт из клиента: `tasks/fbs-wb-emulator/contract-from-client.md`
- README сервиса: `wb_emulator/README.md`
