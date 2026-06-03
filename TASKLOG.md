# TASKLOG

## TASK-36 — 2026-06-03 — MP unload: без блокировки по ТЗ упаковки

- What changed: снята проверка `packaging_instructions_required` при `plan`/`confirm` отгрузки на МП; поле ТЗ на товаре остаётся опциональным.
- What did NOT change: блок `packaging_not_done` при «Отгружено», если есть незавершённое задание упаковки; UI редактирования ТЗ.
- Verification: pytest `test_seller_marketplace_unload`, `test_product_packaging_instructions`.
- Commit: df1934e

## TASK-35 — 2026-05-30 — Упаковка E7 slice 4 (FF каталог, ячейка, отмена, resync)

- What changed: FF-каталог — колонки «Не упак./Упаковано», редактирование ТЗ; создание задания из любой ячейки (не только сортировка); `POST /packaging-tasks/{id}/cancel` для ручных заданий; `pick_resync_warning` (миграция `0037`, sticky при смене подбора с прогрессом); e2e `ff-products` (ТЗ), `ff-packaging-page` (ячейка, отмена).
- What did NOT change: биллинг упаковки; ЧЗ; dismiss предупреждения resync в UI (alert пока открыто задание).
- Verification: `ruff`/`mypy`; pytest 110 passed; `npm run build`; e2e 49 passed; prod deploy `194.87.96.144:8088` (migrations 0036→0037).
- Commit: 6d8647d (main `5c9d115`)

## TASK-34 — 2026-05-30 — Упаковка E7 (этапы 1–3, PR feat/packaging-e7)

- What changed: `packaging_task` API + миграция split unpacked/packed; авто-задание при confirm MP unload; ship блок до `done`; ТЗ `packaging_instructions` (селлер UI + валидация plan/confirm); раздел FF «Упаковка»; create from sorting; прогресс в карточке отгрузки; e2e `ff-packaging-page`, regression MP ship/pick/seller; docs `PACKAGING_RU.md`, TC-NEW-PKG-*.
- What did NOT change: FF-редактирование ТЗ в каталоге; задание из произвольной ячейки; отмена задания; биллинг; ЧЗ.
- Verification: `ruff`/`mypy`; pytest 106 passed; `npm run build`; e2e `ff-packaging-page`, `ff-mp-ship-pick`.
- Commit: 642cba7

## TASK-33 — 2026-05-30 — Упаковка (этап 2: ТЗ селлера, сортировка, валидация MP)

- What changed: `PATCH /products/{id}/packaging-instructions` (селлер/админ); блок `plan`/`confirm` MP unload без ТЗ (`packaging_instructions_required`); `GET /warehouses/{id}/sorting-location`; создание задания без ячейки → зона «Сортировка»; UI селлера — редактирование ТЗ; FF — «Создать задание» на странице упаковки + кнопка «Упаковать» на сортировке; sync упаковки при подборе в короб; pytest `test_product_packaging_instructions.py`; e2e seller-mp-unload/seller-available-stock — ТЗ перед plan.
- What did NOT change: FF-редактирование ТЗ в каталоге; биллинг упаковки; ЧЗ.
- Verification: pytest (packaging + seller MP subset) locally via `.venv`.
- Commit: (pending)

## TASK-32 — 2026-05-30 — Задание на упаковку (этап 1: backend + UI)

- What changed: миграция `0036` — `quantity_unpacked`/`quantity_packed` на остатках; модели/API `packaging_tasks`; авто-задание при confirm отгрузки на МП; блок `ship` до выполнения задания; раздел «Упаковка» в меню ФФ; диалог упаковки из отгрузки на МП; pytest `test_packaging_tasks.py`; e2e `ff-mp-ship-pick` дополнен шагом упаковки. Спека: `docs/PACKAGING_RU.md`.
- What did NOT change: ТЗ на упаковку в карточке товара (поле `packaging_instructions` в БД есть, UI селлера — позже); кнопка «Упаковать» на сортировке; биллинг; ЧЗ.
- Commit: (pending)

## TASK-31 — 2026-05-30 — Пользователи ФФ: добавление и права доступа

- What changed: роль `fulfillment_staff`; таблица `ff_staff_permissions`; API `/auth/staff-accounts` (создание, список, PATCH прав); первый вход с пустым паролем как у селлера; экран «Настройки → Пользователи» с матрицей галочек (настройки, отгрузки МП, приёмка, ячейки, инвентаризация); фильтрация меню по правам; backend-guards на приёмку/отгрузки/ячейки.
- What did NOT change: управление селлерами (только админ); seller portal; полноценный раздел инвентаризации (заглушка).
- Verification: `ruff`/`mypy`; pytest `test_staff_users`; `npm run build`; e2e `ff-staff-users.spec.ts`, `admin-shell-layout`.
- Commit: eb73025

## TASK-30 — 2026-05-29 — Отгрузка на МП: обязательная дата + календарь

- What changed: `planned_shipment_date` обязательна для plan/confirm/ship; селлер не передаёт ФФ без даты; PATCH даты; общий `WmsDateField` (MUI DatePicker) на MP, приёмке селлера/ФФ.
- What did NOT change: создание черновика без даты; логика состава/коробов.
- Verification: `npm run build`; pytest `test_seller_marketplace_unload` (CI).
- Commit: (pending)

## TASK-29 — 2026-05-29 — Отгрузка на МП: единое поле скана (короб / ячейка / товар)

- What changed: убрана отдельная строка «Штрихкод существующего короба»; WHB-скан в общем поле → attach + закрытый короб внизу; ячейка и товар — как раньше в открытую тару.
- What did NOT change: API `/boxes/attach`, backend attach logic, закрытие короба кнопкой.
- Verification: `npm run build`.
- Commit: 88dfd8c

## TASK-28 — 2026-05-27 — Логин: видимая ошибка при неверном портале

- What changed: исправлен «тихий» сброс формы логина — при входе селлера на главный портал ФФ (или админа на `/seller/`) сообщение об ошибке больше не стирается; e2e `auth-portal-mismatch.spec.ts`.
- What did NOT change: правила разделения порталов (селлер → `/seller/`, ФФ → `/`); API auth.
- Verification: `npm run build`; e2e `auth-portal-mismatch`, `auth-core`.
- Commit: 1158a25


- What changed: операция `collect_into_box` — снятие с ячейки и количество в открытый короб в одной транзакции; **«Собрано»** = сумма по всем коробам; скан в короб требует `storage_location_id`; pick/scan товара только при открытом коробе; ручной подбор (модалка) добавляет в открытый короб; UI: сводка «Нужно / Собрано / Осталось», один блок «Сборка в короба», поле кол-ва.
- What did NOT change: создание/утверждение отгрузки селлером; проведение ship по pick allocations; attach inbound-короба (с box_lines).
- Verification: `npm run build` OK; pytest 99 passed (Docker py3.11); e2e — CI.
- Commit: 97c5289

## TASK-26 — 2026-05-27 — Отгрузка на МП: подбор по ячейкам, план/факт, короба WHB

- What changed: подбор **со списанием по ячейкам** — `POST .../pick/scan` (ячейка → товар), `POST .../pick/add`; факт = сумма pick allocations; строки API/UI **план / факт / Δ** (красный при расхождении); отгрузка `ship` с `acknowledge_discrepancy`; сквозные `warehouse_boxes` (ШК `WHB-…`) при создании короба; `POST .../boxes/attach` для существующего короба (разворот в pick); снят лимит «факт ≤ план» при скане; короба не обязательны для ship.
- What did NOT change: operational outbound; создание поставок в WB; seller UI (без подбора).
- Verification: миграция `0034`; pytest 96 passed; e2e 42 passed (`ff-mp-ship-pick`, inbound fixes); prod deploy `194.87.96.144:8088`.
- Commit: fb36cbf

## TASK-25 — 2026-05-27 — FF: отдельный раздел «Отгрузка» (документы на МП)

- What changed: в боковом меню ФФ пункт **«Отгрузка»** (`/app/ff/mp-shipments`) — только документы отгрузки на маркетплейс; из «Поставки и отгрузки» убраны отгрузки на МП и кнопка их создания; дашборд открывает плановую отгрузку в новом разделе.
- What did NOT change: API `marketplace-unload-requests`, логика модалки документа, бэкенд.
- Verification: `npm run build`; e2e `admin-shell-layout`, `ff-mp-ship-pick` (по возможности полный `test:e2e`).
- Commit: bf34625; prod deploy `194.87.96.144:8088`.

## TASK-24 — 2026-05-27 — Сортировка: агрегация по ячейкам

- What changed: блок «Уже в ячейках» — карточка на ячейку (чип + товары под ней); операция «весь короб» — строка «Короб №…» с составом; кнопка «Весь остаток короба сюда» под каждой ячейкой; убрана плоская таблица и колонка «По ячейкам».
- What did NOT change: API putaway.
- Verification: `npm run build`; e2e `ff-reception-sorting`.
- Commit: 4b6be9d

## TASK-23 — 2026-05-27 — Сортировка: история разкладки по ячейкам

- What changed: на карточке короба — блок «Уже в ячейках» (чипы + таблица); колонка «По ячейкам» у строк; fallback для строк без `box_id` при одном коробе; кнопка «Распределить по ячейкам» скрыта в workspace sorting.
- What did NOT change: API putaway и миграции; логика количеств.
- Verification: `npm run build`; e2e `ff-reception-sorting` (assert history chips).
- Commit: d122625

## TASK-22 — 2026-05-27 — Сортировка: разкладка по коробам (целиком и частично)

- What changed: `posted_qty` на строках короба; `box_id` в строках распределения; `POST .../boxes/{id}/putaway` (весь короб или частично); экран **Сортировка** — карточки коробов с составом, «Весь короб в ячейку», частичная разкладка по SKU; приёмка без изменений логики количества.
- What did NOT change: инвентаризация; резерв с зоны сортировки; полный экран «Поставки» (`workspace=full`) — старый черновик распределения с авто-`box_id` при одном коробе.
- Verification: `pytest` test_inbound_distribution + test_inbound_box_intake; `npm run build`; e2e `ff-reception-sorting`, `ff-inbound-distribution`.
- Commit: 2067093

## TASK-21 — 2026-05-27 — Приёмка / Сортировка: зона сортировки и остатки

- What changed: системная ячейка `__SORTING__`; остаток на `verify`; transfer в ячейки через `distribution-complete`; разделы FF **Приёмка** и **Сортировка**; колонки «В сортировке» / «В ячейках» в товарах; API `quantity_in_sorting`; e2e `ff-reception-sorting.spec.ts` (TC-S06-007).
- What did NOT change: инвентаризация для отката количества; резерв с зоны сортировки по-прежнему запрещён.
- Verification: `pytest` 95 passed; `npm run build`; e2e `ff-reception-sorting`, `ff-inbound-cell-hints`.
- Commit: 2de3092

## TASK-20 — 2026-05-25 — Поставка: пустое распределение не оприходует; reopen

- What changed: `complete_distribution` требует строки и полное покрытие принятого (`distribution_incomplete`); `POST .../distribution-reopen` если `posted_qty=0`; UI предупреждение + кнопка «Открыть распределение заново», блок «Завершить» при остатке «без ячейки»; подсказка в каталоге «Товары».
- What did NOT change: логика пересчёта/коробов; ff-catalog по-прежнему только с движениями.
- Verification: `pytest tests/test_inbound_distribution.py` (3 passed); prod deploy `194.87.96.144:8088`.
- Commit: 5998780

## TASK-19 — 2026-05-25 — Селлеры: MUI + email в одной форме

- What changed: `SellersScreen` на MUI (как «Товары»); форма название + email → `POST /sellers` + `POST /auth/seller-accounts` без пароля; `docs/UI_DESIGN_SYSTEM_RU.md`, онбординг в `MVP_DECISIONS_RU.md` + `AGENTS.md`; дашборд — ссылка в «Селлеры».
- What did NOT change: API не отдаёт временный пароль; логика `must_set_password` / первый вход с пустым паролем.
- Verification: `npm run build`; e2e `sellers-create-ui` (полный онбординг); prod deploy.
- Commit: dd1ab61

## TASK-18 — 2026-05-25 — Раздел «Селлеры» в портале FF

- What changed: экран `/app/ff/sellers` — список селлеров и форма «Добавить селлера» (`POST /sellers`); пункт навигации `nav-sellers`; e2e `sellers-create-ui.spec.ts` (TC-S04-001).
- What did NOT change: выдача аккаунта селлера — по-прежнему на дашборде (`POST /auth/seller-accounts`).
- Verification: `npm run build`; e2e `sellers-create-ui`, `admin-shell-layout`; prod deploy `194.87.96.144:8088`.
- Commit: b18340f

## TASK-17 — 2026-05-25 — Резерв без ячейки + накладные (MP + outbound) + deploy

- What changed: складской резерв на submit outbound без ячейки (миграция 0032); post по-прежнему требует ячейку; печать накладной на МП и operational outbound (`printShipmentWaybill.ts`); e2e `ff-mp-print-waybill`, `outbound-print-waybill`; `scripts/deploy/prod-update.sh`, `docker-compose.wms-host-8088.yml`, `docs/DEPLOY_SERVER_RU.md`.
- What did NOT change: seller box composition; consumables inbound; FIFO/FEFO (#14).
- Verification: `ruff`/`mypy`/`pytest` 93 passed; `npm run build`; e2e waybill specs passed.
- Commit: 3a15051

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
