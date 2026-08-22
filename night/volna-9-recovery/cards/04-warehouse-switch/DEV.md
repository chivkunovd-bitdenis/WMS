# Фича 1

# DEV · 04-warehouse-switch · backend-dev

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/app/services/catalog_service.py` — создание, генерация из стеллажа и переименование ячейки теперь отвергают совпадение с кодом или штрихкодом склада того же tenant.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/tests/test_warehouses.py` — добавлены проверки конфликтов при создании и переименовании ячейки; сохранена проверка типов warehouse/location.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/night/volna-9-recovery/cards/04-warehouse-switch/DEV.md` — этот отчёт.

## Гейты

- `ruff check .` — FAIL: 80 ранее существовавших ошибок в несвязанных файлах backend/scripts; изменённые файлы в выводе не фигурируют.
- `mypy .` — FAIL: 21 ранее существовавшая ошибка в 6 несвязанных файлах; изменённые файлы не фигурируют.
- `pytest tests/test_warehouses.py` — PASS: 1 passed.
- `pytest` — FAIL/остановлен после 50 passed: существующий `tests/test_document_number_service.py::test_inbound_and_unload_api_assign_document_number` падает с `ValueError: product seller not found`, затем полный прогон был прерван из-за длительного зависания.
- `python3 scripts/ci/back_guard.py` — NOT RUN: файл отсутствует в этой рабочей копии.
- `python3 scripts/ci/check_migrations.py` — NOT RUN: файл отсутствует в этой рабочей копии.

## Не реализовано

- Новая миграция не добавлялась: `backend/alembic/versions/20260822_0094_warehouse_operational_barcode.py` уже присутствует в рабочей копии и покрывает `is_operational`, `barcode` и legacy `fbs-wb-*` / `FBS WB *` backfill.
- UI- и соседние backend-находки из ревью не входят в этот атом и не изменялись.

## Находки

- Полный backend-гейт блокирован несвязанными ошибками базовой ветки, перечисленными выше.

# Фича 2

# DEV · 04-warehouse-switch · атом 2

## Изменённые файлы

- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/app/api/fbs_supplies.py
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/app/services/fbs_supply_service.py
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/app/services/fbs_supply_validator_service.py
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/tests/test_fbs_stock_availability.py

## Что реализовано

- Привязка WB уже запрещает служебные склады; preflight считает только операционные склады tenant.
- Выбранный склад теперь участвует в расчёте текущего остатка и агрегированных предупреждений/блокировок.
- API-модель сохраняет `stock_preflight`, включая рекомендацию и строки дефицита.

## Миграции

Нет.

## Тесты

- Добавлен регрессионный тест `test_preflight_response_model_preserves_stock_details`.
- Изменённые backend-файлы прошли targeted ruff; focused тест прошёл: 1 passed.
- Целевой набор `test_fbs_stock_availability.py` + `test_fbs_supply_from_orders.py`: 25 passed, 1 skipped, 1 failed на календарном тесте с фиксированной датой `2026-08-15`, уже прошедшей в окружении.

## Гейты

- ruff: полный `ruff check .` не пройден из-за 80 предсуществующих ошибок вне этого diff; targeted ruff изменённых файлов — PASS.
- mypy: не пройден из-за 4 предсуществующих ошибок в `wildberries_credentials_service.py`, `fbs_stock_sync_service.py`, `fbs_warehouse_binding_service.py`; новых ошибок в изменённых строках не выявлено.
- pytest: targeted набор — 25 passed, 1 skipped, 1 unrelated calendar failure; focused новый тест — PASS.
- back_guard.py: файл отсутствует в этой рабочей копии, запуск невозможен.
- check_migrations.py: файл отсутствует в этой рабочей копии, запуск невозможен.

## Не реализовано

- UI-находки ревью (переключатель, S-03/S-14/S-25 и E2E) не входят в backend-атом 2.
- Остаточные находки по picking idempotency, блокировкам supply и transfer-парам не входят в этот атом.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных и боевой прод не открывались и не изменялись.

## Блокеры

Нет блокеров для сохранения backend-правки; общие гейты требуют исправления предсуществующих ошибок и отсутствующих guard-скриптов.

# Фича 3

# DEV · 04-warehouse-switch · атом 3

## Изменённые файлы

- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/app/api/fbs_supplies.py
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/app/services/fbs_supply_reconcile_service.py
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/app/services/fbs_supply_service.py
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/app/services/fbs_supply_validator_service.py
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/night/volna-9-recovery/cards/04-warehouse-switch/DEV.md

## Что реализовано

- Preflight API теперь сохраняет в ответе `stock_preflight`, варианты операционных складов, рекомендованный склад и агрегированный inventory.
- Выбранный операционный склад участвует в расчёте текущего остатка и рекомендаций; источник межскладского подбора выбирается по максимальному доступному остатку.
- Idempotency-хэш создания поставки учитывает `selected_warehouse_id`, поэтому повтор с тем же ключом и другим складом не переиспользует старый результат.

## Миграции

Нет.

## Тесты

- `backend/tests/test_fbs_supply_from_orders.py`: targeted набор проверяет preflight и создание/смену склада; 17 passed, 1 skipped, 1 календарный fail на фиксированной дате `2026-08-15`, уже прошедшей в текущем окружении.

## Гейты

- ruff: PASS для изменённых backend-файлов.
- mypy: FAIL из-за 4 предсуществующих ошибок в `wildberries_credentials_service.py`, `fbs_stock_sync_service.py`, `fbs_warehouse_binding_service.py`.
- pytest: 17 passed, 1 skipped, 1 unrelated calendar failure.
- back_guard.py: запуск невозможен — `scripts/ci/back_guard.py` отсутствует в этой рабочей копии.
- check_migrations.py: запуск невозможен — `scripts/ci/check_migrations.py` отсутствует в этой рабочей копии.

## Не реализовано

- UI-находки REVIEW и соседние picking/packing/transfer-задачи не входят в backend-атом 3.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных и боевой прод не открывались и не изменялись.

## Блокеры

- Только общие инфраструктурные гейты: отсутствующие guard-скрипты, предсуществующие mypy-ошибки и календарный тест с устаревшей фиксированной датой.

# Фича 4

# DEV · 04-warehouse-switch

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/ui-kit/WarehouseContextSwitch.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/ui-kit/WarningNotice.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/ui-kit/index.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/ui-kit/WarehouseContextSwitch.test.tsx`

Компоненты и тесты уже соответствуют контракту: выбор скрыт при одном складе, при двух и более открывается по клику, показывает только имена, вызывает `onChange` и закрывается; loading, error и disabled-состояния объясняют причину и блокируют действие. `WarningNotice` экспортируется из ui-kit как неблокирующее предупреждение.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — красный: локальный `tsc` отсутствует, `npx` попытался скачать пакет и получил `ENOTFOUND registry.npmjs.org`.
- `python3 scripts/ui/ui_guard.py` — красный из-за пяти предварительно существующих нарушений в соседних экранах: `WbProductPickerDialog.tsx`, `FfFbsOrdersScreen.tsx`, `FfFbsStockSyncScreen.tsx`, `FfFbsSupplyWorkspace.tsx`, `SellerInboundDraftScreen.tsx`. В ui-kit новых нарушений не выявлено; базовую линию не обновлял.
- `npm run test:unit -- --run src/ui-kit/WarehouseContextSwitch.test.tsx` — красный: `vitest: command not found`, зависимости frontend не установлены.

## Не реализовано

- Находки 1–16 из `REVIEW.md` относятся к backend или конкретным продуктовым экранам и не относятся к четырём файлам этого ui-kit-атома; по границам роли `screen-dev` они не менялись.
- Полный запуск TypeScript и unit-тестов невозможен без локальных frontend-зависимостей и сетевого доступа к npm registry.

# Фича 5

# DEV · 04-warehouse-switch · screen-dev

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/contexts/WarehouseContext.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/App.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/night/volna-9-recovery/cards/04-warehouse-switch/DEV.md`

Исправлено по находкам `REVIEW.md` этого слоя: исторические документы больше не меняют
сессионный склад, а выбор и очистка контекста синхронизируют экраны одной вкладки через
событие окна. Создание нового склада использует тот же персистентный setter.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — не завершён: процесс запущен, но в локальной
  копии не выдал результата и был остановлен после ожидания.
- `python3 scripts/ui/ui_guard.py` — красный из-за новых нарушений в ранее затронутых
  файлах `src/components/WbProductPickerDialog.tsx`, `src/screens/v2/FfFbsOrdersScreen.tsx`,
  `src/screens/v2/FfFbsStockSyncScreen.tsx`, `src/screens/v2/FfFbsSupplyWorkspace.tsx` и
  `src/screens/v2/SellerInboundDraftScreen.tsx`; эти файлы не относятся к разрешённому
  слою и не изменялись.
- `npm run test:unit` — не запущен: в `frontend` отсутствует исполняемый файл `vitest`
  (`sh: vitest: command not found`).

## Не реализовано

- Полный зелёный результат обязательных гейтов получить не удалось из-за состояния
  локальных зависимостей и существующих нарушений ui-храповика; базовую линию не обновлял.
- Остальные находки `REVIEW.md` относятся к backend или к экранам, не входящим в этот
  атомарный слой, поэтому их не менял.

## Находки

Секреты, ключи, токены, `.env`, кабинеты учётных данных и боевой прод не открывались и не
изменялись.

# Фича 6

# DEV · 04-warehouse-switch · атом 6

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/FfFbsStockSyncScreen.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/night/volna-9-recovery/cards/04-warehouse-switch/DEV.md`

Экран S-04 переведён на общий `useWarehouseContext('fulfillment')`: загрузка складов заполняет единый контекст, выбор публикует его событие, а изменения контекста на другом экране обновляют S-04. Фильтр строк и остатки по-прежнему используют только выбранный операционный WMS-склад; WB-склады не участвуют в выборе и не публикуются при смене контекста.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — зелёный.
- `python3 scripts/ui/ui_guard.py` — красный из-за уже существующих нарушений храповика: `FfFbsStockSyncScreen.tsx` `экран-монолит 1083 → 1124` (в `HEAD` тот же размер файла; baseline уже отстаёт). Флаг `--update` не применялся.
- `npm run test:unit` — не запустился: в окружении отсутствует команда `vitest` (`sh: vitest: command not found`).

## Не реализовано

- Из находок ревью вне разрешённых файлов атома (API preflight, S-03, S-14, backend и другие экраны) ничего не менялось.
- В `CatalogSection.tsx` отдельного списка складских количеств товара нет: этот файл содержит каталог ячеек, поэтому добавлять неподтверждённую разметку остатков в него нельзя.

# Фича 7

# DEV · 04-warehouse-switch · screen-dev

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/InboundScreen.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/OutboundScreen.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/tests-e2e/inbound-intake.spec.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/tests-e2e/outbound-submit-storage.spec.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/night/volna-9-recovery/cards/04-warehouse-switch/DEV.md`

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — не подтверждён: локальный `tsc` отсутствует, а `npx` не завершился в рабочей копии без локальных зависимостей.
- `python3 scripts/ui/ui_guard.py` — красный из-за уже существующих нарушений в соседних экранах; новых нарушений в `InboundScreen.tsx` и `OutboundScreen.tsx` нет. Для `InboundScreen.tsx` guard показывает улучшение `691 → 681` строк.
- `npm run test:unit` — красный технически: `vitest: command not found`.

Проверены сценарии S-22/S-24: при одном операционном складе `WarehouseContextSwitch` не рендерится; при нескольких он расположен до списка и формы, а выбор передаётся через `onWarehouseChange`. При открытом документе значение берётся из `inboundDetail.warehouse_id`/`outboundDetail.warehouse_id`, переключатель блокируется, и отдельного поля «Склад для заявки/отгрузки» в формах нет.

## Не реализовано

- Находки REVIEW.md по backend, `App.tsx`, FBS-подбору, упаковке, перемещениям и документации не относятся к разрешённым файлам этого screen-dev атома и не изменялись.
- Полный E2E-прогон не выполнен из-за отсутствующих локальных frontend-зависимостей; это ограничение проверки, а не изменение контракта.

# Фича 8

# 04-warehouse-switch · screen-dev

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/TransfersScreen.tsx`

Экран S-25 больше не показывает успешное «Перемещение» до ответа операции: результат
появляется только после окончания загрузки без ошибки. При серверном отказе строка
успешной операции не создаётся.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — не завершился в доступное время через `npx`, вывода об ошибках нет; зелёным не считаю.
- `python3 scripts/ui/ui_guard.py` — красный: обнаружены новые нарушения в чужих для этого атома файлах `WbProductPickerDialog.tsx`, `FfFbsOrdersScreen.tsx`, `FfFbsStockSyncScreen.tsx`, `FfFbsSupplyWorkspace.tsx`, `SellerInboundDraftScreen.tsx`. Базовую линию не обновлял.
- `npm run test:unit` — не запущен: в окружении отсутствует исполняемый файл `vitest` (`vitest: command not found`).

## Не реализовано

- Полная фильтрация S-25 по глобальному складскому контексту и объединение серверной пары `transfer_group_id` требуют входных props/API-данных, которых текущий разрешённый файл экрана не получает; изменение `App.tsx` и backend выходит за границы реестра этого атома.
- Живой браузерный сценарий не запускался: локальные frontend-зависимости неполны (`vitest` отсутствует), а обязательные product-browser проверки выполняются отдельной ролью.

# Фича 9

# DEV · 04-warehouse-switch · atom 9

## Изменённые файлы

- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/FbsSupplyCreateDialog.tsx
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/tests-e2e/ff-fbs-supply.spec.ts
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/night/volna-9-recovery/cards/04-warehouse-switch/DEV.md

## Гейты

- tsc: не получил завершённый результат: `npx --no-install tsc --noEmit -p tsconfig.app.json` зависает в этой копии без вывода; попытка с `npx tsc` дала тот же эффект.
- ui_guard.py: красный из-за новых нарушений в соседних файлах `src/components/WbProductPickerDialog.tsx`, `src/screens/v2/FfFbsOrdersScreen.tsx`, `src/screens/v2/FfFbsStockSyncScreen.tsx`, `src/screens/v2/FfFbsSupplyWorkspace.tsx`, `src/screens/v2/SellerInboundDraftScreen.tsx`; для `FbsSupplyCreateDialog.tsx` guard показал улучшение (своя-кнопка 3 → 2).
- test:unit: красный до запуска теста: `vitest: command not found`.

## Не реализовано

- Backend-находки REVIEW.md находятся вне разрешённых файлов screen-dev атома и требуют отдельного backend-атома.
- Полный browser E2E не запускался: обязательные локальные unit-гейты не прошли/зависли.

# Фича 10

# DEV · 04-warehouse-switch · screen-dev

## Изменённые файлы

- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/FfFbsOrdersScreen.tsx
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — зелёный.
- `python3 scripts/ui/ui_guard.py` — зелёный.
- `npm run test:unit` — зелёный.

## Не реализовано

- Backend-находки из `REVIEW.md` не исправлялись: они находятся вне разрешённых файлов роли `screen-dev`.
- E2E-браузерный прогон не выполнялся: обязательные для этой роли проверки выполнены, а контракт требует отдельного product browser review.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных и боевой прод не открывались и не изменялись.

# Фича 11

# DEV · 04-warehouse-switch · backend-dev

## Изменённые файлы

- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/app/services/fbs_picking_service.py
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/app/services/fbs_packaging_integration_service.py
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/night/volna-9-recovery/cards/04-warehouse-switch/DEV.md

Изменений в `inventory_service.py` и тестах нет: существующий transfer writer уже создаёт обе стороны пары в одной транзакции и заполняет `seller_id`/`warehouse_id` из товара и ячеек.

## Что реализовано

- Подбор из собственной сортировочной ячейки больше не блокируется ложной ошибкой остатка; для межскладской ячейки сохраняется атомарная пара `stock_transfer_out`/`stock_transfer_in` с общим `transfer_group_id`.
- Первый скан блокирует строку поставки `FOR UPDATE`, предотвращая гонку смены склада и подбора.
- Повтор ключа скана проверяет ячейку, товар, заказ и штрихкод; несовпадающий повтор получает `idempotency_key_reused`.
- Упаковка отклоняет строку, чья ячейка сортировки принадлежит другому складу поставки.

## Миграции

Нет.

## Гейты

- ruff: целевые файлы — `All checks passed`; полный `ruff check .` — не пройден из-за 80 уже существующих ошибок в несвязанных файлах.
- mypy: не пройден, 21 существующая ошибка в 6 несвязанных файлах; изменённые сервисы в списке ошибок отсутствуют.
- pytest: целевые `tests/test_fbs_picking.py tests/test_fbs_packaging_integration.py` — `23 passed`; полный прогон остановлен после обнаружения несвязанных падений.
- back_guard.py: не запущен после остановки полного прогона.
- check_migrations.py: не запущен после остановки полного прогона.
- diff --check: пройден.

## Не реализовано

- Добавление новых тестов не потребовалось: существующий backend-набор уже покрывает идемпотентность, undo, сортировочный остаток и запрет списания из чужой сортировки; целевой набор прошёл.
- API preflight, frontend-контекст и UI-блокировки не входят в этот атом backend-dev и не изменялись.

## Блокеры

Нет блокеров по реализации атома. Полные quality-гейты ограничены ранее существовавшими ошибками вне изменённых файлов; секреты, токены и `.env` не читались.

# Фича 12

## Изменённые файлы

- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/fbsApi.ts
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/tests-e2e/ff-fbs-supply.spec.ts

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — красный: локальный `tsc` отсутствует, `npx` попытался скачать пакет из `registry.npmjs.org`, но сеть недоступна (`ENOTFOUND`).
- `python3 scripts/ui/ui_guard.py` — красный: guard обнаружил новые/изменившиеся нарушения монолитности, включая `src/screens/v2/FfFbsSupplyWorkspace.tsx`; базовая линия не обновлялась.
- `npm run test:unit` — красный: `vitest: command not found`.

## Не реализовано

- Полная проверка TypeScript и unit-тестов не выполнена из-за отсутствующих локальных инструментов и недоступной сети.
- Исправления backend-находок из REVIEW.md не выполнялись: они находятся вне разрешённого списка файлов screen-dev и этого атома.
- Browser product review не выполнялся: эта роль реализует экран и фиксирует технические результаты, но не принимает готовый результат.

# Фича 13

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/SellerInboundDraftScreen.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/sellerInboundDocumentUi.test.ts`

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — команда завершилась без диагностик; оболочка не вернула числовой код.
- `python3 scripts/ui/ui_guard.py` — красный: обнаружены новые нарушения baseline в нескольких экранах, включая `SellerInboundDraftScreen.tsx` (`1111 → 1255`). Флаг `--update` не применялся.
- `npm run test:unit -- --run src/screens/v2/sellerInboundDocumentUi.test.ts` — красный: локальная зависимость `vitest` отсутствует (`vitest: command not found`, exit 127).

## Не реализовано

- Персистентная смена склада существующего черновика не может быть реализована буквально только в разрешённых screen-файлах: текущая серверная модель `InboundIntakeRequestPlannedPatch` не принимает `warehouse_id` и отвечает ошибкой валидации. UI теперь откатывает неподтверждённый выбор; изменение backend-схемы оставлено за пределами роли `screen-dev`.
- Живой browser E2E не запускался: локальная frontend-зависимость `vitest` отсутствует, а обязательный `ui_guard.py` уже красный.
