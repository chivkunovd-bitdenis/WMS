# TASKLOG

## TASK-57 — 2026-06-16 — Селлер: изоляция каталога по магазину + деплой

- What changed: обычные селлеры всегда видят только свой `seller_id` (JWT-делегирование игнорируется); менеджеры — allowlist (`vitalik`/`vitaliy`/`виталий`, `denmark`/`denmarks`, `WMS_SHOP_MANAGER_EMAILS`, флаг БД); фронт перезагружает каталог при смене активного магазина; WB-импорт ищет баркод только в рамках селлера; pytest `test_seller_wb_catalog_isolation.py`, `test_seller_shop_allowlist.py`.
- What did NOT change: FF-каталог «все селлеры» для админа; логика переключения магазинов у менеджеров.
- Verification: pytest seller isolation 15 passed; PR #40 CI green; `npm run build`.
- Deploy: merge PR #40 → `main` `ee5095c`; prod `194.87.96.144:8088` — `prod-update.sh`, все контейнеры Up, seller/api HTTP 200. WB re-sync прерван (OOM); при необходимости вручную: `./scripts/deploy/sync-all-wb-products.sh`.

## TASK-56 — 2026-06-16 — Честный знак: импорт кодов и печать из упаковки

- What changed: модуль ЧЗ — `marking_codes` / `marking_code_imports` в БД; флаг `requires_honest_sign` у товара; загрузка CSV/PDF селлером или админом ФФ; остатки в разделах «Честный знак» (FF + seller); в задании на упаковке кнопка «Печать ЧЗ» на всё `qty_need_pack` строки, галочка «в 2 экземплярах», повторная печать без списания новых кодов; печать DataMatrix 58×40 (`bwip-js`); блок отгрузки на МП при `marking_not_done`; миграция `20260616_0041`; pytest `test_marking_codes.py`; e2e `ff-marking-packaging.spec.ts`.
- What did NOT change: отчётность в ГИС МТ / API ЧЗ; парсинг PDF-сетки на листе (только постраничный текст + CSV).
- Verification: `ruff check . && mypy . && pytest` (129 passed); `npm run build`; `npx playwright test tests-e2e/ff-marking-packaging.spec.ts`.

## TASK-55 — 2026-06-15 — Портал селлера: переключение между магазинами (Vitality)

- What changed: менеджер-магазинов (email с «vitalik», `WMS_SHOP_MANAGER_EMAILS` или `users.can_manage_seller_shops`) — в сайдбаре раздел «Магазины» с чекбоксами (все селлеры тенанта кроме своего и тестовых `@example.com` / `e2e-*`); после включения — переключатель «Активный магазин»; API `PUT /auth/seller-shops`, `POST /auth/switch-seller`; JWT `seller_id` = активный магазин; все seller API (отгрузки, приёмки, товары, WB) работают от лица выбранного магазина; миграция `20260615_0040`; pytest `test_seller_shop_switch.py`.
- What did NOT change: обычные селлеры без флага — только свой магазин; админ FF не затронут.
- Verification: `pytest tests/test_seller_shop_switch.py`; `npm run build`.

## TASK-54 — 2026-06-14 — Этикетка 58×40 и колонка ШК: баркод WB + размер

- What changed: на этикетке 58×40 в блоке деталей снова печатается «Размер: …»; под штрихкодом — только цифры ШК (баркод WB, не артикул/sku); в колонке «ШК» строк товаров (приёмка, упаковка, отгрузка) — баркод сверху, «Размер: …» снизу; e2e `ff-product-barcode-print.spec.ts` обновлён.
- What did NOT change: отдельная колонка «Размер» в каталоге товаров; логика импорта WB.
- Verification: `npm run build`; `npx playwright test tests-e2e/ff-product-barcode-print.spec.ts`.
- Deploy: commit `476d2aa`, prod `/opt/wms` — `git pull` + rebuild `web` only, `:8088` OK.

## TASK-53 — 2026-06-14 — WB: отдельный товар на каждый размер + фильтр ИП при отгрузке ФФ

- What changed: импорт WB — один `Product` на каждый баркод из `sizes[].skus` (`sku_code` вида `ART/S`, поля `wb_barcode`, `wb_chrt_id`, `wb_size`); при multi-size старый merged SKU → `OLD/…` + `[OLD]` в названии; миграция `20260614_0039`; post-deploy `./scripts/deploy/sync-all-wb-products.sh` (в `prod-update.sh`) — полная загрузка карточек по **всем** селлерам с content-токеном; UI «Товары» — колонка «Размер»; отгрузка на МП (ФФ) — выбор селлера (ИП) перед созданием.
- What did NOT change: строки `OLD/…` не удаляются (остатки/история на них); одна snapshot-карточка WB на nmID.
- Verification: `pytest tests/test_wildberries_legacy_old_mark.py tests/test_wildberries_product_import_sizes.py`; `npm run build`.
- Deploy: `prod-update.sh` → migrate + `python -m app.cli.sync_all_wb_products` в контейнере api.

## TASK-52 — 2026-06-14 — Дубликаты селлеров: очистка prod + атомарное создание

- What changed: prod — удалены 6 пустых дублей «ИП Герус Д.В.» (оставлен один с `gerus_denis@mail.ru`); бэкенд — `POST /sellers/with-account` (селлер + учётка в одной транзакции, откат при `email_taken`); UI `SellersScreen` — один запрос вместо двух; pytest `test_create_seller_with_account_*`; e2e sellers-create / auth-dual / auth-portal-mismatch.
- What did NOT change: отдельные `POST /sellers` и `POST /auth/seller-accounts` (для тестов/API); остальные селлеры (Denmarcs, Виталик и т.д.).
- Verification: `pytest tests/test_sellers.py` — 4 passed; `npm run build` — OK; prod SQL — 1 «ИП Герус Д.В.».
- Deploy: код ещё не на проде — нужен `git pull` + rebuild.

## TASK-51 — 2026-06-11 — Остатки селлера: остаток vs резерв vs отгрузка

- What changed: бэкенд — резерв МП/outbound только по ячейкам (не «Сортировка»); UI селлера — колонки «В ячейках», «Остаток» (На ФФ − резерв), «К отгрузке» (только ячейки); тест `test_available_matches_mp_reserve_only_after_putaway`, e2e `seller-available-stock`.
- What did NOT change: списание при ship/pick МП; экран товаров ФФ.
- Verification: `pytest tests/test_inventory_balances_summary.py`; `npm run build`.

## TASK-50 — 2026-06-11 — Биллинг сотрудников за упаковку

- What changed: ставка за ед. (₽) в настройках сотрудников; расчёт ЗП по завершённым заданиям (только `qty_packed_in_task`, снимок ставки при завершении); фильтр по месяцу (МСК); право «Упаковка» в матрице доступа; API `PATCH /auth/staff-accounts/{id}/packaging-rate`; миграция `0038`.
- What did NOT change: биллинг селлеров (литр‑день), выплаты/бухгалтерия.
- Verification: `ruff` / `mypy` / `pytest tests/test_staff_packaging_billing.py`; `npm run build`; e2e `ff-staff-packaging-billing.spec.ts`; PR #37 CI green; prod `194.87.96.144:8088` commit `b646463`.
- Commit: b646463 (squash PR #37).

## TASK-49 — 2026-06-11 — Упаковка: таблица создания задания как в приёмке

- What changed: диалог «Создать задание на упаковку» — ширина `min(1200px, 96vw)` как у `WbProductPickerDialog` в приёмке; те же отступы таблицы; фиксированные ширины колонок количества; `minWidth: 180` у «Наименование» в `FfProductLineCells` (не ломается посимвольно).
- What did NOT change: API упаковки, логика создания задания.
- Verification: `npm run build` — OK.
- Commit: 405025f.

## TASK-48 — 2026-06-11 — Отдельный favicon и марка для портала селлера

- What changed: `frontend/public/favicon-seller.svg` — бирюзовый «магазин» (отличается от фиолетовой «коробки» FF); `seller/index.html` → `/favicon-seller.svg`; `WmsBrandMark` с `portal="seller"` в шапке селлера и на экране входа; `deploy/Caddyfile.http` — исключение favicon-seller из no-cache SPA.
- What did NOT change: favicon FF (`/favicon.svg`), API, бизнес-логика.
- Verification: `npm run build` — OK.

## TASK-47 — 2026-06-11 — Брендинг WMS: favicon и марка в UI

- What changed: `frontend/public/favicon.svg` — вместо розовой молнии (оцифровка) иконка коробки в цвете темы; `WmsBrandMark` в шапке FF/селлера и на экране входа; заголовки вкладок `WMS · Фулфилмент` / `WMS · Селлер`.
- What did NOT change: API, бизнес-логика.
- Verification: `npm run build`; CI green PR #34; prod deploy `194.87.96.144:8088` commit `4caef80` — `curl /favicon.svg` → коробка `#5b21b6`.
- Commit: 4caef80 (squash PR #34).

## TASK-46 — 2026-06-11 — Seller SPA: no-cache на :8088 (Caddyfile.http)

- What changed: `deploy/Caddyfile.http` — `Cache-Control: no-cache` для seller/FF HTML (как в `frontend/deploy/Caddyfile`), чтобы после деплоя браузер не держал старый `seller-*.js`.
- What did NOT change: логика `SellerMarketplaceUnloadDialog` (на сервере уже `seller-mp-add-products`).
- Verification: после merge — `curl -I http://194.87.96.144:8088/seller/` → no-cache; hard refresh у селлера → кнопка «Добавить товары».

## TASK-45 — 2026-06-11 — WbProductPickerDialog: FF приёмка и отгрузка на МП

- What changed: `SellerWbProductPickerDialog` → ядро `WbProductPickerDialog` с `variant="ff"` (`FfProductLineCells`, печать ШК); подключено в `FfInboundRequestView` и `FfSuppliesShipmentsPage`. Пропсы `applyLabel`, `renderTrailingHeadCells` / `renderTrailingBodyCells` для будущих колонок FF.
- What did NOT change: API; логика сохранения строк остаётся в родительских экранах.
- Verification: `npm run build`; e2e ff-dashboard, ff-inbound-boxes, seller-mp-unload, seller-cabinet — 8 passed; prod `194.87.96.144:8088` commit `9094acf`.
- Commit: 9094acf.

## TASK-44 — 2026-06-11 — Общий picker каталога WB для селлера

- What changed: `SellerWbProductPickerDialog` — единая модалка выбора товаров (поиск, категория, фото, qty); подключена в `SellerInboundDraftScreen` и `SellerMarketplaceUnloadDialog`. Отгрузка на МП передаёт `showAvailableColumn`, `filterRow`, `getAvailable`.
- What did NOT change: портал ФФ — подключён в TASK-45.
- Verification: `npm run build`; e2e seller-mp-unload, seller-available-stock, seller-cabinet, ff-inbound-boxes.
- Commit: 4cb7c33 (в prod вместе с 9094acf).

## TASK-43 — 2026-06-11 — Селлер: отгрузка на МП — добавление товаров как в приёмке

- What changed: в `SellerMarketplaceUnloadDialog` убрана старая таблица всех остатков; кнопка «Добавить товары» + модалка каталога WB (поиск, категория, фото, ШК, колонка «Доступно») как в `SellerInboundDraftScreen`; строки заявки редактируются в таблице с удалением. E2e `seller-mp-unload`, `seller-available-stock` обновлены.
- What did NOT change: API отгрузки на МП; портал ФФ (уже на новом паттерне).
- Verification: `npm run build`; e2e `seller-mp-unload.spec.ts`, `seller-available-stock.spec.ts` — 2 passed.

## TASK-42 — 2026-06-11 — Отгрузка на МП: видимая панель добавления + деплой

- What changed: панель «Добавление товаров» (скан ШК + «Добавить товары») перенесена **под склад WB, до таблицы строк**; Caddy `no-cache` для `index.html`; e2e проверяет отсутствие старого Select на МП.
- What did NOT change: логика модалки каталога и API строк (c8db069); акты расхождений.
- Verification: PR #33 CI green; prod `194.87.96.144:8088` commit `d3a951e`, bundle `ff-CC085PGz.js`.
- Commit: d3a951e (squash merge PR #33).

## TASK-41 — 2026-06-11 — Отгрузка на МП: добавление товаров как в приёмке

- What changed: в черновике отгрузки на МП — скан ШК/артикула, кнопка «Добавить товары» и модалка каталога WB (фото, артикулы, ШК, поиск, категория, кол-во) как в `FfInboundRequestView`; строки таблицы по-прежнему через `FfProductLineCells`. Старый Select по остаткам убран для МП.
- What did NOT change: сборка в короба, подбор по ячейкам, акты расхождений (там старый Select).
- Verification: `npm run build`; e2e `ff-dashboard.spec.ts`, `ff-mp-ship-pick.spec.ts`.
- Commit: c8db069; CI run 27307241687 success; prod deploy `194.87.96.144:8088`.

## TASK-40 — 2026-06-11 — Этикетка ШК 58×40 по макету WB (штрихкод сверху)

- What changed: макет термоэтикетки как на WB — штрихкод и цифры сверху, имя селлера, название, артикул, цвет, бренд, «Пожалуйста оставьте отзыв»; убраны EAC и строка размера. API каталога отдаёт `wb_brand` из карточки WB.
- What did NOT change: печать коробов/ячеек; накладные A4; размер по-прежнему в каталоге, но не на этикетке.
- Verification: `npm run build`; pytest `test_wb_card_enrichment`, `test_seller_wb_catalog_enriched_from_imported_card`; e2e `ff-product-barcode-print.spec.ts`.
- Commit: b5e3eba; prod deploy `194.87.96.144:8088`.

## TASK-39 — 2026-06-10 — Приёмка без обязательного короба; этикетка: размер/цвет WB

- What changed: пересчёт приёмки — факт по строкам вручную даже при коробах; короб опционален. Этикетка 58×40 — убрано «Производитель: Россия», добавлены `wb_size`/`wb_color` из карточки WB в каталог и печать.
- What did NOT change: печать коробов/ячеек; синхронизация WB.
- Verification: pytest inbound_box + wb_catalog; e2e `ff-inbound-box-intake`, `ff-product-barcode-print`.
- Commit: 47ab877

## TASK-38 — 2026-06-10 — Этикетка товара 58×40 (EAC, артикул, количество)

- What changed: печать по образцу WB — 58×40 мм, название (обрезка), «Артикул», «Производитель: Россия», знак EAC, CODE128; диалог с превью и полем «Количество этикеток»; API `GET /products/linked-wb-catalog` — баркоды до первого движения по складу.
- What did NOT change: этикетки ячеек/коробов; накладные A4.
- Verification: pytest `test_linked_wb_catalog_before_stock_movement`; e2e `ff-product-barcode-print.spec.ts`.

## TASK-37 — 2026-06-10 — Печать ШК товара в модалках FF (приёмка, сортировка, отгрузка, упаковка)

- What changed: единый блок строки товара (фото, артикул, ШК WB, артикул продавца, nm, название) + кнопка «Печать ШК» (CODE128, 58×40) в модалках приёмки, сортировки, отгрузки на МП и упаковки; каталог WB подтягивается через `useWbProductCatalog`.
- What did NOT change: печать ШК ячеек/коробов; накладные A4; синхронизация карточек WB.
- Verification: `npm run build`; e2e `ff-product-barcode-print.spec.ts` (TC-NEW-PRINT-01).

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
