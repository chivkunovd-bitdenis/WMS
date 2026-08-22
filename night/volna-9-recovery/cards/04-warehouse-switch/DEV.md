# Фича 1

# DEV · 04-warehouse-switch · backend-dev

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/app/models/warehouse.py` — добавлены `is_operational` и уникальный штрихкод склада.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/app/services/catalog_service.py` — список ограничен операционными складами; резолвер различает склад и ячейку, отклоняет коллизии и ограничивает tenant.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/app/api/warehouses.py` — API возвращает новые поля и тип результата `warehouse`/`location`, ошибки резолвера отдаются понятными кодами HTTP.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/alembic/versions/20260822_0094_warehouse_operational_barcode.py` — добавляет признаки, генерирует штрихкоды, помечает legacy `fbs-wb-*`/`FBS WB *` служебными и оставляет один основной склад операционным.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/tests/test_warehouses.py` — проверяет список, скан склада, скан ячейки и коллизию.

## Миграции

- `20260822_0094` — добавляет `warehouses.is_operational` и `warehouses.barcode`, backfill-ит значения, помечает legacy-склады служебными и создаёт уникальный индекс штрихкода.

## Тесты

- `backend/tests/test_warehouses.py` — 1 тест прошёл: операционный список, типы `warehouse`/`location`, коллизия возвращает `409 barcode_ambiguous`.

## Гейты

- ruff: PASS для изменённых backend-файлов; полный `ruff check .` — FAIL на 84 ранее существующих ошибках, включая unrelated-файлы.
- mypy: FAIL на 25 ранее существующих ошибках в 7 файлах; в затронутых модель/API/catalog-файлах ошибок нет.
- pytest: PASS для `tests/test_warehouses.py` (1 passed); полный прогон не запускался из-за baseline-ошибок quality gates.
- back_guard.py: НЕ ЗАПУЩЕН — файл отсутствует в `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/scripts/ci/`.
- check_migrations.py: НЕ ЗАПУЩЕН — файл отсутствует в `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/scripts/ci/`.

## Не реализовано

- Остальные атомарные куски карточки 04 не реализованы: изменён только операционный склад и разрешение складского штрихкода.
- UI-переключатель, контекст сессии и интеграция с рабочими экранами не входят в роль backend-dev и не изменялись.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных и боевой прод не читались и не изменялись.

## Блокеры

- Guard-скрипты отсутствуют в этой рабочей копии; это отмечено в гейтах. Код и целевой тест проверены локально.

# Фича 2

# DEV · 04-warehouse-switch · backend-dev

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/app/services/fbs_warehouse_binding_service.py` — активная WB→WMS-привязка отклоняет служебный склад кодом `warehouse_not_operational`.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/app/services/fbs_stock_availability_service.py` — запрос физического остатка учитывает только `Warehouse.is_operational = true`, поэтому служебные склады не попадают в доступный FBS-остаток.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/app/services/fbs_supply_validator_service.py` — preflight суммирует остаток по операционным складам tenant, выбирает склад по покрытию с приоритетом текущего при равенстве и возвращает агрегированные warning/blocking строки.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/tests/test_fbs_stock_availability.py` — существующие проверки доступного FBS-остатка; целевой модуль проверен после изменений.

## Миграции

Нет в этом атомарном куске: признак `Warehouse.is_operational` добавлен зависимостью `04-A`.

## Гейты

- `ruff check .`: не запускался в полном объёме; `ruff check` трёх изменённых сервисов — PASS.
- `mypy .`: не запускался в полном объёме; отдельный результат предыдущего backend-прохода зафиксирован как BLOCKED существующими ошибками вне этого куска.
- `pytest`: целевой `backend/tests/test_fbs_stock_availability.py` — PASS, 6 passed.
- `back_guard.py`: недоступен в рабочей копии (`scripts/ci/back_guard.py` отсутствует).
- `check_migrations.py`: недоступен в рабочей копии (`scripts/ci/check_migrations.py` отсутствует).

## Не реализовано

- UI-предупреждения, выбор склада и визуальная разбивка не входят в backend-dev и не изменялись.
- Новая API-ручка не добавлялась: данные preflight расширены в существующем ответе.

## Находки

Секреты, ключи, токены, `.env` и кабинеты учётных данных не читались.

## Блокеры

Нет блокеров для backend-части этого атомарного куска.

# Фича 3

# DEV · 04-warehouse-switch · atom 3

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/app/services/fbs_supply_service.py` — добавлен импорт `Warehouse`, необходимый существующей проверке операционного склада при смене склада поставки.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/tests/test_fbs_supply_from_orders.py` — добавлен интеграционный тест смены склада до первого pick и отказа после pick; проверено сохранение склада документа.

Endpoint `PATCH /operations/fbs-supplies/{supply_id}/warehouse` и сервисная логика атома уже были реализованы предыдущим backend-атомом; в рамках этого прохода они покрыты тестом и исправлена отсутствующая зависимость импорта.

## Миграции

Нет. Схема базы данных не менялась.

## Тесты

- `test_fbs_supply_warehouse_switch_is_locked_after_pick` — новая поставка меняет склад на второй операционный склад до pick; после установки статуса pick повторная смена возвращает HTTP 409 с причиной `Склад закреплён: подбор уже начат`; workspace сохраняет выбранный склад.

## Гейты

- ruff: FAIL на существующих ошибках вне изменённых файлов (80 ошибок, включая старые `noqa`, импортные блоки и ошибки в `scripts/`); изменённые файлы новых нарушений не добавили.
- mypy: FAIL на существующих ошибках вне изменённых файлов (`inventory_movement_report_service.py`, `wildberries_credentials_service.py`, `scripts/`, `fbs_stock_sync_service.py`, `fbs_warehouse_binding_service.py`, `wildberries_product_import_service.py`).
- pytest: targeted `tests/test_fbs_supply_from_orders.py -k warehouse_switch` PASS (`1 passed`); полный прогон остановлен после обнаружения ранее существующих падений в `test_fbs_autopoll.py` и `test_fbs_openapi_contract.py`.
- back_guard.py: не запущен — файл отсутствует в checkout (`/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/scripts/ci/back_guard.py`).
- check_migrations.py: не запущен — файл отсутствует в checkout (`/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/scripts/ci/check_migrations.py`); миграций в изменениях нет.

## Не реализовано

- Вне атома 3 ничего не менялось: UI, фильтрация списков и межскладской pick относятся к другим атомам и не реализуются этой ролью.

# Фича 4

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/ui-kit/WarehouseContextSwitch.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/ui-kit/WarningNotice.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/ui-kit/index.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/ui-kit/WarehouseContextSwitch.test.tsx`

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — красный: локальный `tsc` отсутствует, а загрузка через `npx` невозможна из-за отсутствия сети (`ENOTFOUND registry.npmjs.org`).
- `python3 scripts/ui/ui_guard.py` — красный на уже существующих нарушениях вне разрешённых файлов: `src/components/WbProductPickerDialog.tsx`, `src/screens/v2/FfFbsSupplyWorkspace.tsx`, `src/screens/v2/SellerInboundDraftScreen.tsx`. Новых нарушений в изменённых ui-kit-файлах не выявлено.
- `npm run test:unit` — красный: локальный бинарник `vitest` отсутствует (`vitest: command not found`).

## Не реализовано

Буквально не проверено только прохождение обязательных локальных гейтов из-за отсутствующих зависимостей и недоступной сети. Реализация контракта добавлена: переключатель скрывается при 0–1 варианте, открывает список имён, вызывает `onChange` и закрывается после выбора; загрузка и недоступность объясняются оператору, ошибка выводится через `ErrorNotice`, `WarningNotice` остаётся неблокирующим.

Отдельный Git-коммит не создан: среда запрещает запись `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-1-04-warehouse-switch/index.lock` (`Operation not permitted`).

# Фича 5

# DEV · 04-warehouse-switch · screen-dev

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/utils/fbsWarehouse.ts` — фильтрация операционных складов и выбор сохранённого/первичного склада.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/contexts/WarehouseContext.tsx` — сессионный контекст склада для FF и селлера с очисткой при logout.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/App.tsx` — подключён контекст FF и очищен выбор при выходе.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/apps/seller/SellerApp.tsx` — подключён отдельный контекст селлера, без глобального фильтра заявок.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — не подтверждён: локальный `tsc` отсутствует, а `npx` завис без результата в среде без доступной установки зависимостей.
- `python3 scripts/ui/ui_guard.py` — красный на существующих нарушениях вне изменённых файлов: `src/components/WbProductPickerDialog.tsx`, `src/screens/v2/FfFbsSupplyWorkspace.tsx`, `src/screens/v2/SellerInboundDraftScreen.tsx`; новых нарушений в изменённых файлах не выявлено. `src/App.tsx` стал меньше по размеру.
- `npm run test:unit` — красный: `vitest: command not found`.

## Не реализовано

- Визуальный `WarehouseContextSwitch` и отдельные экранные фильтры не изменялись: они относятся к уже реализованному UI-kit-атому и другим атомарным кускам карточки.
- Полный запуск типизации и unit-тестов невозможен без локальных зависимостей; сеть для их установки недоступна.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных и боевой прод не читались и не изменялись.

# Фича 6

# DEV · 04-warehouse-switch · screen-dev

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/FfFbsStockSyncScreen.tsx` — добавлен контекст выбранного операционного склада, фильтрация отображаемых WB-привязок и `EmptyState` для нулевого числа рабочих складов.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — не подтверждён: локальный `npx` не вернул результат в доступное время, установка зависимостей в среде недоступна.
- `python3 scripts/ui/ui_guard.py` — красный: существующие нарушения в `src/components/WbProductPickerDialog.tsx`, `src/screens/v2/FfFbsSupplyWorkspace.tsx`, `src/screens/v2/SellerInboundDraftScreen.tsx`; для изменённого `src/screens/v2/FfFbsStockSyncScreen.tsx` guard также отметил рост монолитного экрана. Базовую линию не обновлял.
- `npm run test:unit` — красный: `vitest: command not found`.

## Не реализовано

- S-01 не расширялся отдельной товарной таблицей: переданный `CatalogSection` не содержит таблицы товарных остатков, а уже существующий выбор склада применяет склад к доступным складским данным и ячейкам. Добавление нового источника данных вышло бы за границы этого экранного куска.
- E2E-сценарий для переключения не добавлен: для него требуется тестовая фикстура с несколькими операционными WMS-складами и привязками, а локальный `test:unit` не запускается из-за отсутствующего `vitest`.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных и боевой прод не читались и не изменялись.

# Фича 7

# DEV · 04-warehouse-switch · atom 7 · screen-dev

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/InboundScreen.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/OutboundScreen.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/tests-e2e/inbound-intake.spec.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/tests-e2e/outbound-submit-storage.spec.ts`

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — PASS, команда завершилась без ошибок.
- `python3 scripts/ui/ui_guard.py` — FAIL: новые нарушения обнаружены в чужих файлах `src/components/WbProductPickerDialog.tsx`, `src/screens/v2/FfFbsStockSyncScreen.tsx`, `src/screens/v2/FfFbsSupplyWorkspace.tsx` и `src/screens/v2/SellerInboundDraftScreen.tsx`; `InboundScreen.tsx` улучшен. Эти файлы не входят в атом и не изменялись.
- `npm run test:unit` — FAIL до запуска тестов: `vitest: command not found`.

## Не реализовано

- Полное переключение контекста из строки S-22/S-24 не подключено на уровне родительского состояния: текущие экранные пропсы не передают callback выбора склада, а изменение файлов вне реестра этого атома запрещено. Переключатель подключён к существующему ui-kit и принимает опциональный `onWarehouseChange`; при одном складе строка и второй выбор полностью отсутствуют.
- Сценарий с двумя складами и записью выбранного склада в новый документ не добавлялся: для этого требуется передать callback из родительского контейнера и отдельная E2E-фикстура с двумя операционными складами, что выходит за список файлов атома.

# Фича 8

## Изменённые файлы

- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/TransfersScreen.tsx
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/tests-e2e/transfer-and-outbound.spec.ts

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — выполнялся, процесс не завершился в отведённое время; итог не подтверждён.
- `python3 scripts/ui/ui_guard.py` — красный из-за уже существующих/несвязанных новых нарушений в `WbProductPickerDialog.tsx`, `FfFbsStockSyncScreen.tsx`, `FfFbsSupplyWorkspace.tsx` и `SellerInboundDraftScreen.tsx`; эти файлы не входят в разрешённые файлы S-25.
- `npm run test:unit` — красный: в окружении отсутствует команда `vitest` (`vitest: command not found`).

## Не реализовано

- Полная фильтрация строк S-25 текущим складом и раскрытие реальной межскладской пары не реализованы буквально: текущий экран получает только `locations`, `products` и POST-обработчик, без списка движений, названий складов или выбранного складского контекста; доступный API также отклоняет перемещение между разными складами. В разрешённых файлах добавлено единое видимое представление отправленной операции «из ячейки → в ячейку» и e2e-проверка этого результата.

# Фича 9

## Изменённые файлы

- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/fbsApi.ts
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/FbsSupplyCreateDialog.tsx
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/night/volna-9-recovery/cards/04-warehouse-switch/DEV.md

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — зелёный (команда завершилась без диагностик).
- `python3 scripts/ui/ui_guard.py` — красный из-за существующих нарушений в соседних экранах и нового ограничения монолита/стилей этого экрана; базовая линия не обновлялась.
- `npm run test:unit -- --run src/screens/v2/FbsSupplyCreateDialog.test.ts` — красный: в окружении отсутствует команда `vitest` (`vitest: command not found`).

## Не реализовано

- В контрактном списке складских строк оставлена обратная совместимость: если backend не вернул `inventory`, `warehouse_options` или `recommended_warehouse`, диалог сохраняет прежний summary без выдуманных остатков.
- Живой браузерный e2e не запускался, поскольку обязательный unit-runner отсутствует в окружении; существующий e2e-файл не изменялся, так как его сценарии требуют backend-полей и относятся к следующему интеграционному проходу.

# Фича 10

## Изменённые файлы

- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/FfFbsOrdersScreen.tsx
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/night/volna-9-recovery/cards/04-warehouse-switch/DEV.md

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` из `frontend/` — зелёный.
- `python3 scripts/ui/ui_guard.py` из корня — красный: guard сообщает новые превышения монолитности в `FfFbsOrdersScreen.tsx` (1608 строк) и `FfFbsSupplyWorkspace.tsx` (2507 строк), а также нарушения в соседних файлах; базовая линия не обновлялась.
- `npm run test:unit` из `frontend/` — красный: в окружении отсутствует `vitest` (`vitest: command not found`).

## Не реализовано

- Буквальная смена склада консолидации в рабочем месте не подключена: доступный `FbsWorkspace` содержит только склад документа, а разрешённые файлы карточки не включают API-клиент или backend-контракт для передачи нового `warehouse_id`. Реализован показ контекста и блокировка смены после начала поставки.
- Новые e2e/unit-сценарии не добавлялись: unit-runner отсутствует, а изменение `fbsApi.ts` для передачи WMS-фильтра запрещено списком файлов карточки.

# Фича 11

# DEV · 04-warehouse-switch · backend-dev

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/app/services/fbs_picking_service.py` — разрешён скан ячейки другого операционного склада; подтверждённый pick создаёт перенос в сортировку склада поставки, повтор ключа идемпотентен, undo использует обратную пару.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/app/services/inventory_service.py` — межскладской transfer сохраняет обе записи `stock_transfer_out`/`stock_transfer_in` с общим `transfer_group_id`.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/app/services/fbs_packaging_integration_service.py` — удалён упаковочный обход в чужую сортировку; без остатка в сортировке упаковка блокируется.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/tests/test_fbs_picking.py` — существующие проверки pick/undo использованы как регрессия атомарного движения.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/tests/test_fbs_packaging_integration.py` — проверки упаковки обновлены под запрет списания из чужой сортировки и без подтверждённого остатка.

## Миграции

Нет. Использованы существующие поля `InventoryMovement.transfer_group_id` и складские модели.

## Тесты

- `backend/tests/test_fbs_picking.py` и `backend/tests/test_fbs_packaging_integration.py` — 23 passed: pick, повтор idempotency key, undo и блокировка упаковочного обхода.

## Гейты

- ruff: PASS для всех изменённых backend-файлов и тестов; полный `ruff check .` — FAIL на 82 существующих ошибках вне этого куска.
- mypy: FAIL на 21 существующей ошибке в 6 несвязанных файлах; новых ошибок в затронутых сервисах по целевой проверке не выявлено.
- pytest: PASS, 23 passed для целевых тестов.
- back_guard.py: НЕ ЗАПУЩЕН — `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/scripts/ci/back_guard.py` отсутствует.
- check_migrations.py: НЕ ЗАПУЩЕН — `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/scripts/ci/check_migrations.py` отсутствует.

## Не реализовано

- Новые API-роуты не добавлялись: изменения встроены в существующие операции pick и упаковки.
- UI и экранный контекст склада не изменялись: это вне роли backend-dev.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных и боевой прод не читались и не изменялись.

## Блокеры

- Полные quality gates ограничены baseline-ошибками и отсутствующими guard-скриптами; целевой backend-срез проверен.

# Фича 12

# DEV · 04-warehouse-switch · screen-dev

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/fbsApi.ts` — добавлен тип и клиентский вызов `GET /warehouses/resolve`.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx` — скан склада меняет контекст и сбрасывает ячейку, скан ячейки выбирает родительский склад, `ScannerLine` сообщает следующий шаг, успешный pick показывает единственную строку «Взято…».
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/ui-kit/ScannerLine.tsx` — проверен и использован без изменения.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/tests-e2e/ff-fbs-supply.spec.ts` — мок resolver и проверки текстов сканера/результата.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` из `frontend/` — красный: `npx` не нашёл локальный `tsc` и попытался обратиться к registry.npmjs.org; сеть недоступна (`ENOTFOUND`).
- `python3 scripts/ui/ui_guard.py` из корня — красный на baseline-нарушениях монолитности, включая `FfFbsSupplyWorkspace.tsx` (2493 → 2519 строк); базовая линия не обновлялась.
- `npm run test:unit` из `frontend/` — красный: `vitest: command not found`.

## Не реализовано

- `ScannerLine` не менялся: существующего ui-kit-примитива достаточно для контрактного поведения.
- Полноценный новый e2e-сценарий смены склада не добавлялся: текущий контрактный мок содержит один склад, а изменение ограничено разрешёнными файлами и существующим потоком workspace.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных и боевой прод не читались и не изменялись.

# Фича 13

# DEV · 04-warehouse-switch · screen-dev · feature 13

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/SellerInboundDraftScreen.tsx` — выбор склада только в новой заявке/черновике при двух и более доступных операционных складах; выбор сохраняется в черновике, после передачи отображается только имя.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/sellerInboundDocumentUi.test.ts` — проверки видимости выбора склада для одного/нескольких складов и статуса черновика.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` из `frontend/` — зелёный.
- `python3 scripts/ui/ui_guard.py` из корня — красный: базовая проверка сообщает о существующих нарушениях в других экранах и о росте монолитности `SellerInboundDraftScreen.tsx` из-за реализации в разрешённом экранном файле; baseline не обновлялся.
- `npm run test:unit -- --run src/screens/v2/sellerInboundDocumentUi.test.ts` из `frontend/` — красный до запуска тестов: `vitest: command not found`.

## Не реализовано

- E2E-сценарий в `seller-cabinet.spec.ts` не расширен: браузерный тест-runner зависит от отсутствующего локального `vitest`, а полноценная фикстура с двумя операционными складами требует backend-данных вне разрешённых файлов этого атома.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных и боевой прод не читались и не изменялись.
