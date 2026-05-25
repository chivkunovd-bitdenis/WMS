# TASKLOG

## TASK-16 — 2026-05-25 — Outbound submit: ячейка обязательна (#13)

- What changed: `submit` outbound возвращает `lines_missing_storage`, если у строки нет ячейки; решение в `MVP_DECISIONS_RU.md`; UI — обязательная ячейка при добавлении, форма в draft, блокировка кнопки submit; RU-сообщения в `readApiErrorMessage`; pytest + e2e `outbound-submit-storage.spec.ts`.
- What did NOT change: soft-reserve на уровне склада; seller submit outbound (по-прежнему только admin API).
- Verification: pytest `test_outbound_submit_storage.py`; e2e `outbound-submit-storage.spec.ts`; `npm run build`.
- Commit: 906bfd8

## TASK-15 — 2026-05-25 — Селлер: доступный остаток в UI (#15)

- What changed: экран «Товары» в портале селлера — колонки остаток, зарезерв., доступно и подсказка `(доступно N)` при резерве; e2e `seller-available-stock.spec.ts` (TC-S09-001); `TC_AUTOMATION_COVERAGE` / EN test-case note.
- What did NOT change: API `inventory-balances/summary`; MP-диалог (уже показывал «Доступно на ФФ»); operational outbound у селлера.
- Verification: `npm run build` ok; e2e `seller-available-stock.spec.ts` passed.
- Commit: c608196

## TASK-14 — 2026-05-25 — Хвосты MP unload + prod celery beat

- What changed: UI «Изменено ФФ» (`ff_modified`) в списке и карточке отгрузки на МП; `celery_beat` в `docker-compose.prod.yml` / `docker-compose.yml`; расписание `wms.wb_mp_warehouses_daily_sync` (03:00 UTC); плановая дата отгрузки на МП в общем списке FF.
- What did NOT change: operational outbound в кабинете селлера; деплой на сервер (вручную `git pull` + compose prod).
- Verification: `ruff`/`mypy` celery_app; `npm run build` ok.
- Commit: e31fd17

## TASK-13 — 2026-05-24 — Отгрузка на МП от селлера (TC-NEW-MP)

- What changed: отдельный документ `marketplace_unload` (не operational outbound): селлер — таблица остатков, plan/unplan, резерв; FF — confirm → короба/подбор/ship; дашборд ФФ по `submitted`; lazy-sync складов WB; миграция 0031, резервы; e2e `seller-mp-unload`, обновлены `ff-mp-ship-pick`, `ff-dashboard`.
- What did NOT change: индикатор `ff_modified` в UI; celery beat для daily WB sync; operational outbound в кабинете селлера.
- Verification: `pytest` 92 passed; `npm run build` ok; e2e seller-mp-unload, ff-mp-ship-pick, smoke passed; docker `compose build` + `up -d` (api, web, web_seller, celery_worker).
- Commit: 8c5a1c6

## TASK-12 — 2026-05-23 — Печать ШК ячейки и поиск по штрихкоду (US-C-03, US-C-06)

- What changed: кнопка печати ШК у выбранной ячейки в распределении FF; поле «Добавить по ШК» + Enter в picker; каталог FF = `/products` + WB-поля из `ff-catalog`; v2 inbound: поиск по ШК в `wb-catalog` merge, авто-выбор SKU; util `resolveProductByBarcode.ts`; e2e TC-NEW-C03/C06.
- What did NOT change: US-C-07 печать накладной приёмки.
- Verification: build ok; e2e barcode-add, distribution, inbound-intake passed.
- Commit: ac8f5ad

## TASK-11 — 2026-05-23 — Зелёные строки и «без ячейки» (US-C-04, US-C-05)

- What changed: строка товаров FF зелёная при `actual_qty === expected_qty` (`ff-inbound-line-row-match`); блок «Остаток без ячейки» — warning-фон и `data-pending=1` при нераспределённом остатке; e2e TC-NEW-C04/C05 в существующих spec.
- What did NOT change: v2 InboundScreen; глобальный список остатков (US-E-04).
- Verification: build ok; e2e box-intake + distribution 3 passed.
- Commit: 2aaae47

## TASK-9 — 2026-05-23 — Поштучная приёмка по скану короба INB (US-C-01)

- What changed: миграция `0029` (`inbound_intake_box_lines`, `intake_opened_at`/`intake_closed_at` на коробах); API `POST .../boxes/open`, `.../boxes/{id}/scan`, `.../close`; агрегация `actual_qty` по сканам; блок ручного PATCH actual при наличии коробов; UI на `FfInboundRequestView` и `InboundScreen`; pytest `test_inbound_box_intake.py` + хелпер `inbound_box_intake_helpers.py`; e2e `ff-inbound-box-intake.spec.ts` (TC-NEW-C01); обновлены регрессионные тесты/e2e под box-scan.
- What did NOT change: подсказки ячеек (US-C-02), зелёные строки, предварительные остатки только по коробам, состав короба от селлера.
- Verification: `pytest` 86 passed; `npm run build` ok; e2e 3 passed (`ff-inbound-box-intake`, `ff-inbound-distribution`).
- Commit: a9cebe6

## TASK-10 — 2026-05-23 — Подсказки ячеек при распределении (US-C-02)

- What changed: `GET /operations/inventory-balances/locations-by-product`; чипы «Уже лежит: A-01 (N)» в блоке распределения FF (`FfInboundRequestView`), клик подставляет ячейку; pytest `test_product_location_hints.py`; e2e `ff-inbound-cell-hints.spec.ts` (TC-NEW-C02).
- What did NOT change: подсказки при поштучном скане в короб (только этап распределения); v2 InboundScreen.
- Verification: pytest 87 passed; e2e cell-hints 1 passed; build ok.
- Commit: a453666

## TASK-8 — 2026-05-22 — Внутренние ШК на короба поставки (US-B-02)

- What changed: таблица `inbound_intake_boxes`, генерация N коробов с `INB-{hex}` при primary-accept; API `boxes` в заявке и `POST .../boxes/{id}/mark-label-printed`; UI панель «Короба и внутренние ШК» с печатью; миграция `0028`; pytest расширен; e2e TC-NEW-B02 в `ff-inbound-boxes.spec.ts`.
- What did NOT change: скан короба на поштучной приёмке (US-C-01), паллетирование, предварительное увеличение остатков только по коробам.
- Verification: `pytest tests/test_inbound_box_acceptance.py` (3 passed); `npm run test:e2e -- tests-e2e/ff-inbound-boxes.spec.ts` (5 passed, TC-NEW-B01/B02).
- Commit: pending

## TASK-7 — 2026-05-22 — Приёмка по коробам (US-B-01 / US-A-01)

- What changed: поля `planned_box_count` / `actual_box_count` / `boxes_discrepancy` на заявке поставки; селлер указывает план коробов в черновике; ФФ принимает факт на этапе «Принято по коробам»; предупреждение при расхождении; миграция `0027`; merge `0026`; pytest `test_inbound_box_acceptance.py`; e2e `ff-inbound-boxes.spec.ts` (TC-NEW-B01).
- What did NOT change: внутренние ШК на короба (US-B-02), предварительное увеличение остатков только по коробам, паллетирование >10 коробов.
- Verification: `pytest tests/test_inbound_box_acceptance.py`; `npm run build`; Docker `api`+`web` пересобраны.
- Commit: pending

## TASK-6 — 2026-05-22 — Отгрузка на МП: подбор по ячейкам и списание при «Отгружено»

- What changed: статус `shipped` и `POST .../ship` списывает остатки по сохранённому подбору (товар × ячейка); `PUT .../pick-allocations` сверяет сумму с фактом скана в коробах; UI — «Начать подбор», «Утвердить заявку» (без списания), «Отгружено»; миграция `0025`; e2e `ff-mp-ship-pick.spec.ts` (TC-NEW-MP-01).
- What did NOT change: ТЗ упаковки в карточке товара, статус «Начата сборка», расходники, откат отгрузки, приёмка по коробам.
- Verification: `pytest tests/test_marketplace_unload_and_discrepancy_acts.py`; `npm run build`; `npm run test:e2e -- ff-mp-ship-pick.spec.ts ff-dashboard.spec.ts`.
- Commit: pending

## TASK-5 — 2026-05-03 — Production Docker Compose HTTPS via Caddy

- What changed: production `docker-compose.prod.yml` now publishes `80/443` for Caddy, persists ACME state in Docker volumes, and passes `WMS_PUBLIC_DOMAIN` into the `web` container; production Caddy site blocks use the public domain for automatic HTTPS; added `deploy/env.prod.example` and updated README production instructions for DNS + HTTPS.
- What did NOT change: application code, database schema/migrations, Celery task definitions, and dev `docker-compose.yml` behavior were not changed in this task.
- Verification: `WMS_PUBLIC_DOMAIN=example.com POSTGRES_PASSWORD=postgres JWT_SECRET_KEY=dev-secret WMS_SECRETS_FERNET_KEY=dev-fernet DATABASE_URL='postgresql+psycopg_async://postgres:postgres@db:5432/wms' docker compose -f docker-compose.prod.yml config --quiet`; `ruff check . && mypy . && pytest` in `backend/`; `npm run build` in `frontend/`.
- Commit: 20b1aef

## TASK-3 — 2026-05-03 — Post accepted seller inbound distribution into FF stock

- What changed: completing FF inbound distribution now creates inventory movements and balances from distributed actual quantities, so accepted seller products appear in the FF warehouse catalog.
- What did NOT change: seller private WB catalog import, marketplace shipment flows, billing, migrations, and Docker infrastructure were not changed in this task.
- Verification: `ruff check app/services/inbound_intake_service.py tests/test_inbound_distribution.py && mypy app/services/inbound_intake_service.py`; `pytest tests/test_inbound_distribution.py tests/test_products_wb_catalog.py`.
- Commit: d5a954f

## TASK-2 — 2026-05-03 — Split seller and FF product catalogs

- What changed: renamed the FF products endpoint to `/products/ff-catalog` and changed FF catalog visibility to products with warehouse movements only; seller `/products/wb-catalog` remains private to the seller role.
- What did NOT change: seller WB import mechanics, marketplace shipment stock movements, adjustment acts, billing, and docker-compose infrastructure were not changed in this task.
- Verification: `ruff check app/api/products.py app/services/seller_wb_catalog_service.py tests/test_products_wb_catalog.py && mypy app/api/products.py app/services/seller_wb_catalog_service.py`; `pytest tests/test_products_wb_catalog.py`; `npm run build`; `npm run test:e2e -- ff-products.spec.ts`.
- Commit: 4089d7e

## TASK-1 — 2026-05-03 — FF products catalog

- What changed: added the fulfillment admin products catalog screen with seller filtering, sorting by product name/stock, WB photo/barcode enrichment, and backend/admin API coverage.
- What did NOT change: marketplace shipment stock movements, adjustment acts, billing, and docker-compose infrastructure were not changed in this task.
- Verification: `ruff check . && mypy . && pytest` in `backend/`; `npm run build` and `npm run test:e2e` in `frontend/`.
- Commit: 728e894
