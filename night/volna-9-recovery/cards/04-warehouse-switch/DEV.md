# Фича 1

# DEV · 04-warehouse-switch · backend-dev

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/app/models/warehouse.py` — добавлен ORM-default для генерируемого штрихкода.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/app/services/catalog_service.py` — создание склада отклоняет конфликт кода с существующим складом или ячейкой того же tenant.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/alembic/versions/20260822_0094_warehouse_operational_barcode.py` — legacy `fbs-wb-*` / `FBS WB *` не повышаются обратно до операционных.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/tests/test_warehouses.py` — проверены отказ коллизии и тип разрешённой ячейки.

## Гейты

- `ruff`: FAIL на полном backend из-за 80 ранее существующих нарушений; изменённые файлы отдельно проходят проверку.
- `mypy`: FAIL на 21 ранее существующей ошибке в 6 файлах; ошибок в изменённых файлах нет.
- `pytest`: `tests/test_warehouses.py` — PASS, 1 passed.
- `back_guard.py`: не запущен — файл отсутствует в этой рабочей копии по ожидаемому пути `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/scripts/ci/back_guard.py`.
- `check_migrations.py`: не запущен — файл отсутствует в этой рабочей копии по ожидаемому пути `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/scripts/ci/check_migrations.py`.

## Не реализовано

- Остальные находки из `REVIEW.md` не относятся к этому backend-атому (межскладские измерения 07-A, preflight/picking/supply и frontend) и не изменялись.

## Находки

- Секреты, токены, `.env`, кабинеты учётных данных и боевой production не читались и не изменялись.
- Коммит невозможен: Git не разрешил создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-1-04-warehouse-switch/index.lock` (`Operation not permitted`), поэтому SHA отсутствует.

# Фича 2

# DEV · 04-warehouse-switch · backend-dev

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/app/services/fbs_supply_validator_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/tests/test_fbs_stock_availability.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/night/volna-9-recovery/cards/04-warehouse-switch/DEV.md`

## Что реализовано

Preflight FBS исключает резервы выбранных заказов при расчёте доступного остатка каждого операционного склада. Поэтому остаток, уже зарезервированный выбранным заказом, не вычитается повторно: достаточный общий остаток не превращается в ложную блокировку.

Добавлен регрессионный тест на доступность выбранного заказа с существующим резервом.

## Миграции

Нет.

## Гейты

- `ruff check backend/app/services/fbs_supply_validator_service.py backend/tests/test_fbs_stock_availability.py` — PASS.
- `ruff check .` из `backend/` — FAIL на существующих несвязанных файлах; затронутые файлы проходят.
- `mypy .` из `backend/` — FAIL на существующих несвязанных файлах; ошибок в изменённых файлах нет.
- Целевой pytest `tests/test_fbs_stock_availability.py -k selected_fbs_order_reservation_can_be_excluded` — PASS (1 passed).
- Полный `pytest` — прерван после 307 passed, 4 skipped и 5 existing failures; падения: `test_fbs_manual_pick.py`, `test_fbs_openapi_contract.py`, `test_fbs_orders_intake.py`, `test_fbs_packaging_fulfillment.py`, `test_fbs_stock_emulator_integration.py`.
- `python3 scripts/ci/back_guard.py` — FAIL: файл отсутствует в данной рабочей копии.
- `python3 scripts/ci/check_migrations.py` — FAIL: файл отсутствует в данной рабочей копии.
- `git diff --check` — PASS.

## Не реализовано

- Остальные находки REVIEW не относятся к этому атомарному backend-слою и не изменялись: измерения `InventoryMovement`, миграция barcode/legacy-складов, API-модели preflight, picking/packing guards, смена склада поставки, frontend и реестр UI-блокировок.

## Находки

- В рабочей копии присутствуют несвязанные изменения в `night/volna-9-recovery/JOURNAL.md`; они не включены в этот результат.

# Фича 3

# DEV · 04-warehouse-switch · атом 3

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/app/api/fbs_supplies.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/app/services/fbs_supply_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/tests/test_fbs_supply_from_orders.py`

## Реализовано

- API принимает `selected_warehouse_id` для preflight и создания поставки; поставка создаётся на выбранном операционном складе.
- Смена склада нетронутой поставки выполняется под блокировкой строки; `in_delivery` и `done` также считаются закреплёнными.
- Добавлен регрессионный тест создания поставки на вручную выбранном складе; существующий сценарий lock-after-pick проверен.

## Миграции

Нет.

## Гейты

- `ruff check backend/app/api/fbs_supplies.py backend/app/services/fbs_supply_service.py backend/tests/test_fbs_supply_from_orders.py` — PASS.
- `ruff check .` — FAIL: 80 ранее существующих ошибок в несвязанных файлах репозитория.
- `mypy .` — FAIL: ранее существующие ошибки в `inventory_movement_report_service.py`, `wildberries_credentials_service.py`, cleanup-скриптах и других несвязанных файлах.
- `pytest -q tests/test_fbs_supply_from_orders.py -k 'warehouse_switch or selected_operational'` — PASS, 2 passed, 17 deselected.
- `pytest -q` — запущен; итог записывается после завершения процесса.
- `python3 scripts/ci/back_guard.py` — ожидает завершения полного pytest-прогона.
- `python3 scripts/ci/check_migrations.py` — ожидает завершения полного pytest-прогона.
- `git diff --check` — PASS.

## Не реализовано

- Общие поля `InventoryMovement.seller_id/warehouse_id`, миграция и межскладские движения не изменялись: это зависимость 07-A/отдельный атом, не часть атома 3.
- Полный контракт `warehouse_options`/`inventory` preflight не расширялся: текущий атом касается выбора склада при создании и смены склада документа.

## Блокеры или находки

- Полные ruff/mypy гейты блокируются существующими ошибками вне изменённых файлов. Секреты, ключи, токены и `.env` не читались.

# Фича 4

# screen-dev · 04-warehouse-switch

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/ui-kit/WarehouseContextSwitch.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/ui-kit/WarningNotice.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/ui-kit/index.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/ui-kit/WarehouseContextSwitch.test.tsx`

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — зелёный, команда завершилась с кодом 0.
- `python3 scripts/ui/ui_guard.py` — красный: обнаружены новые нарушения в соседних файлах `src/components/WbProductPickerDialog.tsx`, `src/screens/v2/FfFbsOrdersScreen.tsx`, `src/screens/v2/FfFbsStockSyncScreen.tsx`, `src/screens/v2/FfFbsSupplyWorkspace.tsx`, `src/screens/v2/SellerInboundDraftScreen.tsx`; эти файлы не входят в атом и не изменялись.
- `npm run test:unit` — красный: `vitest: command not found`, локальные зависимости отсутствуют.

## Не реализовано

Замечания `REVIEW.md` относятся к backend и соседним экранам; они не входят в слой этого атома и не изменялись по границам роли `screen-dev`. Проверка `ui_guard.py` также выявила нарушения в соседних экранах, которые нельзя исправлять в этой карточке.

# Фича 5

# DEV · 04-warehouse-switch

## Изменённые файлы

- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/utils/fbsWarehouse.ts
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/App.tsx
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/apps/seller/SellerApp.tsx
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/night/volna-9-recovery/cards/04-warehouse-switch/DEV.md

Изменения сохраняют операционный склад в сессионном контексте, выбирают первичный склад при его наличии, исключают служебные `FBS WB *`, очищают контекст при выходе и передают обработчик переключения в приёмку и отгрузку. Подстановки `warehouses[0]` в разрешённых файлах убраны.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — красный: локального `tsc` нет; `npx --no-install` не смог найти бинарник и попытался обратиться к `registry.npmjs.org`, сеть недоступна (`ENOTFOUND`).
- `python3 scripts/ui/ui_guard.py` — красный: зафиксированы новые нарушения в соседних файлах, не изменённых этой карточкой: `src/components/WbProductPickerDialog.tsx`, `src/screens/v2/FfFbsOrdersScreen.tsx`, `src/screens/v2/FfFbsStockSyncScreen.tsx`, `src/screens/v2/FfFbsSupplyWorkspace.tsx`, `src/screens/v2/SellerInboundDraftScreen.tsx`. Baseline не обновлялся.
- `npm run test:unit` — красный: `vitest: command not found`, зависимости фронтенда в рабочей копии не установлены.

## Не реализовано

- Переключение склада внутри `FfFbsSupplyWorkspace` из находки REVIEW не исправлялось: этот экран не входит в разрешённые файлы атома; редактирование соседнего экрана нарушило бы границы роли `screen-dev`.
- Требуемые проверки не стали зелёными из-за отсутствующих локальных инструментов/зависимостей и несвязанных нарушений `ui_guard.py`; исправлять их через изменение baseline запрещено инструкцией роли.

# Фича 6

# DEV · 04-warehouse-switch · screen-dev

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/FfFbsStockSyncScreen.tsx` — непривязанные WB-склады остаются видимыми при выборе любого операционного склада, чтобы оператор мог создать первую привязку; привязанные строки по-прежнему фильтруются выбранным складом.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/night/volna-9-recovery/cards/04-warehouse-switch/DEV.md` — обязательный отчёт screen-dev.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend` — не подтверждён: команда не вывела результат в рабочей копии.
- `python3 scripts/ui/ui_guard.py` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch` — не подтверждён: команда не вывела результат в рабочей копии.
- `npm run test:unit` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend` — не подтверждён: команда не вывела результат в рабочей копии.
- `git diff --check` — зелёный.

## Не реализовано

- Остальные находки из `REVIEW.md` относятся к backend, другим экранам или документации и не входят в разрешённый слой этого атома.
- Полный браузерный сценарий с двумя операционными складами не добавлялся: контракт разрешает только перечисленные файлы, а существующий e2e-файл не содержит готового сценария для настройки двух складов без изменений за пределами этого атома.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных и боевой прод не читались и не изменялись.

# Фича 7

# DEV · 04-warehouse-switch · screen-dev

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/InboundScreen.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/OutboundScreen.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/night/volna-9-recovery/cards/04-warehouse-switch/DEV.md`

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — не подтверждён: `npx` не завершился в рабочей копии без доступного локального `tsc`, процесс остановлен.
- `python3 scripts/ui/ui_guard.py` — красный из-за пяти существующих нарушений в соседних экранах: `WbProductPickerDialog.tsx`, `FfFbsOrdersScreen.tsx`, `FfFbsStockSyncScreen.tsx`, `FfFbsSupplyWorkspace.tsx`, `SellerInboundDraftScreen.tsx`. В изменённом `InboundScreen.tsx` нарушение стало меньше (`691 → 681` строк); новых нарушений в изменённых файлах guard не сообщил.
- `npm run test:unit` — не запущен: `vitest: command not found`.

## Не реализовано

- Backend-находки REVIEW.md не относятся к разрешённым файлам этого screen-dev атома и не изменялись.
- Полный живой E2E-прогон не выполнен: локальные frontend-зависимости для unit/TypeScript отсутствуют.

# Фича 8

## Изменённые файлы

- Изменений в продуктовых файлах нет.
- Артефакт: `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/night/volna-9-recovery/cards/04-warehouse-switch/DEV.md`

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — не удалось получить подтверждённый результат: процесс `npx` завершился без вывода и статуса в отведённое время.
- `python3 scripts/ui/ui_guard.py` — красный из-за новых нарушений в несвязанных экранах `WbProductPickerDialog.tsx`, `FfFbsOrdersScreen.tsx`, `FfFbsStockSyncScreen.tsx`, `FfFbsSupplyWorkspace.tsx`, `SellerInboundDraftScreen.tsx`; S-25 не указан среди нарушений.
- `npm run test:unit` — красный: `vitest: command not found`.

## Не реализовано

- Полная фильтрация строк S-25 текущим складом и раскрытие межскладской пары не легли буквально. `TransfersScreen` получает только `locations`, `products` и обработчик POST, без списка движений, названий операционных складов и выбранного сессионного контекста. Добавление этих данных потребовало бы правки `App.tsx`/API вне разрешённых файлов атома.
- Текущий экран поддерживает только обычное перемещение между ячейками и показывает подтверждение последней операции без UUID. Межскладской pick с одной раскрываемой парой должен быть поставлен после передачи в экран необходимых данных от зависимых атомов 4, 5 и 11.

# Фича 9

# DEV · 04-warehouse-switch

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/FbsSupplyCreateDialog.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/night/volna-9-recovery/cards/04-warehouse-switch/DEV.md`

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — не подтверждён: процесс не завершился без вывода и был остановлен после ожидания.
- `python3 scripts/ui/ui_guard.py` — красный по пяти уже затронутым соседним монолитам из рабочей копии; для `FbsSupplyCreateDialog.tsx` новых нарушений нет, файл стал лучше по правилу собственной кнопки (`3 → 2`). Базовую линию не обновлял.
- `npm run test:unit -- --run src/screens/v2/FbsSupplyCreateDialog.test.ts` — не запустился: в рабочей копии отсутствует команда `vitest` (`vitest: command not found`).

## Не реализовано

- Backend-находки 1–7 и 12–13 из `REVIEW.md` не менялись: они находятся за пределами разрешённых файлов этого screen-dev атома.
- Фронтовые находки по `FfFbsSupplyWorkspace.tsx`, `App.tsx`, `FfFbsOrdersScreen.tsx` и `FfFbsStockSyncScreen.tsx` не менялись: эти файлы не входят в разрешённый список атома.
- Полный зелёный результат gate-проверок невозможно подтвердить из-за незавершившегося `tsc` и отсутствующего локального `vitest`; исходный ui_guard содержит новые нарушения в соседних файлах, не добавленные этим изменением.
- Коммит не создан: Git отклонил создание `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-1-04-warehouse-switch/index.lock` с ошибкой `Operation not permitted` в ограниченной рабочей среде.

# Фича 10

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/FfFbsOrdersScreen.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx`

S-03 теперь получает независимый список операционных складов, не строит варианты из текущих строк и сохраняет выбранный WMS-контекст в пределах сессии. Рабочее место показывает доступные операционные склады, меняет склад черновой поставки через существующий PATCH и блокирует смену после начала операции с объяснением.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — зелёный.
- `python3 scripts/ui/ui_guard.py` — красный: храповик сообщил новые нарушения размера монолита в `FfFbsOrdersScreen.tsx` и `FfFbsSupplyWorkspace.tsx` (также сообщил нарушения в несвязанных экранах). Базовая линия не обновлялась.
- `npm run test:unit -- --run src/screens/v2/FfFbsSupplyWorkspace.test.ts` — не запущен: в рабочей копии отсутствует исполняемый `vitest` (`vitest: command not found`).
- `git diff --check` — зелёный.

## Не реализовано

- Тесты в `/frontend/src/screens/v2/FfFbsSupplyWorkspace.test.ts` и `/frontend/tests-e2e/ff-fbs-supply.spec.ts` не расширялись: локальный unit-runner отсутствует, а атомарная правка ограничена двумя экранами из слоя screen-dev.
- Находка 13 (`docs/blockers/S-03.md`) не внесена: файл не входит в разрешённый список экранного атома и относится к документационному слою.
- Бэкенд-находки 1–8 и 11–12 не входят в роль `screen-dev` и не изменялись.

# Фича 11

# DEV · 04-warehouse-switch · атом 11

## Изменённые файлы

- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/app/models/inventory_movement.py
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/app/services/inventory_service.py
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/app/services/fbs_picking_service.py
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/tests/test_fbs_picking.py
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/alembic/versions/20260822_0095_inventory_movement_dimensions.py

## Реализовано

- Пустая исходная ячейка больше не создаёт фиктивный `fbs_order_pick`: pick отклоняется с `insufficient_unpacked`.
- Каждая запись движения фиксирует `seller_id` и `warehouse_id`, а миграция добавляет и заполняет эти измерения для существующей истории.
- Существующий идемпотентный transfer-путь и undo-пара сохранены; упаковка продолжает списывать только из `PackagingTaskLine.storage_location_id`.

## Тесты

- `test_fbs_pick_empty_location_is_rejected` проверяет отказ пустой ячейки и отсутствие записи pick.
- Полный целевой набор `tests/test_fbs_picking.py tests/test_fbs_packaging_integration.py`: 23 passed.

## Гейты

- ruff: targeted files — passed; полный `ruff check .` — не пройден из-за 80 существующих ошибок вне изменённых файлов.
- mypy: не пройден из-за 4 существующих ошибок в `wildberries_credentials_service.py`, `fbs_stock_sync_service.py`, `fbs_warehouse_binding_service.py`; в изменённых файлах новых ошибок не показано.
- pytest: targeted — passed, 23 passed.
- back_guard.py: недоступен в этой рабочей копии (`scripts/ci/back_guard.py` отсутствует).
- check_migrations.py: недоступен в этой рабочей копии (`scripts/ci/check_migrations.py` отсутствует).

## Не реализовано

- Полные repository-гейты `ruff`, `mypy`, `back_guard.py` и `check_migrations.py` нельзя подтвердить из-за существующих ошибок и отсутствующих скриптов.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных и боевой прод не открывались и не изменялись.

# Фича 12

# DEV · 04-warehouse-switch · screen-dev

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/tests-e2e/ff-fbs-supply.spec.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/night/volna-9-recovery/cards/04-warehouse-switch/DEV.md`

Изменён только экран рабочего места FBS и его пользовательский E2E-сценарий. Повторный товарный скан получает стабильный ключ для той же ячейки и заказа, поэтому повтор запроса возвращает прежний результат. Сценарий также проверяет скан склада, последующий выбор ячейки и неизменность строки «Взято…» при повторе.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — не подтверждён: локальный процесс `npx` завис без вывода и был остановлен после ожидания; результат не объявляю зелёным.
- `python3 scripts/ui/ui_guard.py` — КРАСНЫЙ: храповик сообщил новые нарушения в `WbProductPickerDialog.tsx`, `FfFbsOrdersScreen.tsx`, `FfFbsStockSyncScreen.tsx`, `FfFbsSupplyWorkspace.tsx` и `SellerInboundDraftScreen.tsx`. Базовую линию не обновлял.
- `npm run test:unit` — КРАСНЫЙ: `vitest: command not found`.
- `git diff --check` — зелёный.

## Не реализовано

- Полный продуктовый browser review не выполнялся: роль screen-dev ограничена кодом и обязательными локальными gate-командами.
- `frontend/src/screens/v2/fbsApi.ts` и `frontend/src/ui-kit/ScannerLine.tsx` не потребовали изменений: существующие resolver/client и текстовые состояния уже соответствуют контракту.

# Фича 13

# DEV · 04-warehouse-switch · screen-dev · feature 13

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/SellerInboundDraftScreen.tsx` — добавлена защита seller-портала от отображения служебных складов `FBS WB *`; выбор и подпись используют только доступные операционные склады.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/sellerInboundDocumentUi.test.ts` — добавлена проверка, что служебный склад не попадает в варианты селлера.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/night/volna-9-recovery/cards/04-warehouse-switch/DEV.md` — этот отчёт.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend` — не завершён: процесс не вывел результат и был остановлен после ожидания; ошибок TypeScript в выводе нет.
- `python3 scripts/ui/ui_guard.py` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch` — красный: зафиксирован рост монолита `SellerInboundDraftScreen.tsx` `1111 → 1251`, а также ранее существующие/чужие для этого атома нарушения в `WbProductPickerDialog.tsx`, `FfFbsOrdersScreen.tsx`, `FfFbsStockSyncScreen.tsx`, `FfFbsSupplyWorkspace.tsx`. Baseline не обновлялся.
- `npm run test:unit -- --run src/screens/v2/sellerInboundDocumentUi.test.ts` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend` — красный до запуска теста: `vitest: command not found`.

## Не реализовано

- Полный browser-сценарий с двумя операционными складами не запускался: локальный test runner не установлен (`vitest` отсутствует), а успешная browser-проверка требует доступного backend/e2e окружения. Основная логика выбора и сохранения черновика уже присутствовала в предыдущем атоме и не менялась.
- Находок про секреты, ключи, токены, `.env`, кабинеты учётных данных или боевой прод нет: такие материалы не открывались.
