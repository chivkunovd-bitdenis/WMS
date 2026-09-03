# 01 — Аудит: что переносим в мобильное приложение

Дата аудита: 2026-07-02. Источники: `backend/app/api/*.py`, `frontend/src/screens/ff/*`,
`docs/BUSINESS_PROCESS_SELLER_INBOUND_OUTBOUND_RU.md`.

## Вывод в одну строку

Бэкенд полностью готов для всех трёх флоу (приёмка, сортировка, отгрузка) — мобилке
нужен только клиент к существующим эндпоинтам. Новых эндпоинтов для v1 не требуется,
кроме, возможно, PIN-логина (см. «API gaps»).

## Карта операций

### 1. Приёмка (inbound intake)

Веб-экраны: `FfInboundQueuePage`, `FfInboundRequestView`, `FfInboundBoxAddDialog`.
База API: `/operations/inbound-intake-requests`

Бизнес-флоу на складе:
1. Сотрудник видит список запланированных поставок → выбирает заявку.
2. **Первичная приёмка по коробам:** фиксирует факт количества коробов,
   создаёт короба (у каждого internal_barcode), печатает/клеит этикетки.
3. **Приёмка по товарам:** скан ШК короба → короб «открыт» → сканирует товары
   в короб (+1 за скан) → закрывает короб. Товар без короба — «loose intake».
4. Завершение приёмки → verify → расхождения план/факт фиксируются автоматически.

Ключевые эндпоинты (все в `backend/app/api/inbound_intake.py`):
- `GET  /operations/inbound-intake-requests` — список (фильтры по статусу)
- `GET  /operations/inbound-intake-requests/{id}` — детали + строки + короба
- `POST .../{id}/boxes` — создать короб (create_inbound_box)
- `POST .../{id}/boxes/open-by-barcode` — открыть короб сканом (open_inbound_box_by_barcode)
- `POST .../{id}/boxes/{box_id}/scan` — скан товара в короб (scan_product_into_inbound_box)
- `PUT  .../{id}/boxes/{box_id}/lines/{line_id}` — ручная правка qty (set_inbound_box_line_quantity)
- `POST .../{id}/boxes/{box_id}/close` — закрыть короб (close_inbound_box_intake)
- `POST .../{id}/scan-loose` — скан в «без короба» (scan_barcode_to_loose_intake)
- `POST .../{id}/complete-receiving` — завершить приёмку
- `POST .../{id}/verify` — завершить проверку
- `POST .../{id}/boxes/{box_id}/label-printed` — отметка «этикетка напечатана»
> Точные пути сверять с декораторами в файле — выше названия функций, путь читать из кода
> или из `openapi.json` (это обязанность исполнителя тикета).

### 2. Сортировка (размещение по ячейкам)

Веб-экран: `FfInboundSortingPanel` (внутри `FfInboundRequestView`).
Это продолжение inbound-заявки: распределение принятого товара из коробов и
loose-пула по ячейкам хранения (storage locations) или «Без ячейки».

Бизнес-флоу:
1. Скан ШК короба (или выбор товара из loose-пула).
2. Скан ШК ячейки (у ячеек есть barcode — тип `LocationRow` в сортинг-панели).
3. Ввод/подтверждение количества → размещение (distribution).
4. Прогресс: remaining_qty по коробу/товару до нуля.

Ключевые эндпоинты:
- `POST .../{id}/boxes/{box_id}/putaway` — putaway_inbound_box
- distributions по ячейкам (см. `_dist_out`, эндпоинты распределения в inbound_intake.py)
- `POST .../{id}/resync-sorting-stock` — resync_inbound_sorting_stock
- `GET /warehouses/...` — ячейки склада (locations c barcode)

### 3. Отгрузка (marketplace unload + упаковка)

Веб-экраны: `FfSuppliesShipmentsPage`, `FfMarketplaceUnloadBoxAddDialog`, `FfPackagingPage`.
База API: `/operations/marketplace-unload-requests` + `/operations/packaging-tasks`

Бизнес-флоу:
1. Список заявок на отгрузку (подтверждённые ФФ) → выбор заявки.
2. **Отбор (pick):** `POST .../{id}/pick/scan` — скан товара из ячейки, +1 к отобранному;
   `POST .../{id}/pick/add` — добавление без скана (админ-фоллбек);
   `PUT .../{id}/pick-allocations` — распределение по ячейкам.
3. **Упаковка в короба:** `POST .../{id}/boxes` (+ `/boxes/batch`, `/boxes/attach`),
   `POST .../{id}/boxes/{box_id}/scan` — скан товара в короб,
   `.../boxes/{box_id}/close`, `.../copy`, `.../manual-line`, удаление.
4. **Маркировка (Честный Знак):** packaging-tasks: `confirm-packed`, `pack`,
   `complete`; печать кодов — `/operations/marking-codes/...` (scan_print_marking_codes,
   verify_marking_pair). В мобилке v1 — только проверка пары (scan-verify), печать
   остаётся на стационарных принтерах.
5. **Завершение:** `POST .../{id}/submit` → `POST .../{id}/ship` (списание остатков).

Правило скана (из бизнес-дока, строго): скан ШК не из заявки → понятная ошибка,
количество НЕ менять. Ручной ввод вместо скана запрещён для рядового сотрудника.

### Вне скоупа v1 (не делаем, не трогаем)

- `outbound_shipment.py` — legacy, веб ФФ его не использует (проверено grep'ом по фронту).
- Инвентаризация, перемещения (`stock_transfer`) — v2.
- Акты расхождений, дашборды, настройки, печать шаблонов — остаются в вебе.
- Селлерский портал — не для ТСД вообще.

## Авторизация

- `POST /auth/login` (email+пароль) → `TokenResponse`; `GET /auth/me`.
- Staff-аккаунты: `/auth/staff-accounts` — сотрудники ФФ уже есть как сущность.
- Мобильный паттерн: устройство общее, у сотрудника PIN. **API gap G1** (см. ниже).
  Для v1 допустимо: полный логин email+пароль один раз (запоминается на устройстве),
  повторный вход в смену — по локальному PIN, привязанному к сохранённому токену.
  Это НЕ требует изменений бэкенда → gap G1 откладывается.

## API gaps (что может понадобиться добавить в бэкенд)

- **G1 (отложено):** серверный PIN-логин для staff. V1 обходится локальным PIN.
- **G2 (проверить в ходе реализации):** эндпоинт разрешения «что это за ШК» —
  универсальный lookup barcode → product | box | location. Если его нет, мобильные
  экраны сортировки будут дёргать несколько эндпоинтов. Проверить `products.py` /
  `inventory_balances.py` на предмет поиска по barcode.
- **G3 (nice to have):** счётчики для главного экрана (сколько поставок ждёт приёмки,
  сколько отгрузок в работе) — можно собрать из существующих списков на клиенте.

## Технические факты для исполнителей

- OpenAPI-схема: FastAPI отдаёт `/openapi.json` — из неё генерируется Kotlin-клиент.
- Аутентификация: Bearer token в `Authorization`.
- Локальный запуск бэка: `docker compose up -d --build` (порт из docker-compose.yml)
  или SQLite-режим на 18080 (см. README.md).
- Ошибки API читаются как в вебе: `readApiErrorMessage` — формат detail-строк.
