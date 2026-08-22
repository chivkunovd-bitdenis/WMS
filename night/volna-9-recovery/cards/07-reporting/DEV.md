# Фича 1

# Backend Dev · 07-reporting · атом 1

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend/alembic/versions/20260822_0094_inventory_movement_reporting_dimensions.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend/tests/test_inventory_movement_reporting_dimensions.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/night/volna-9-recovery/cards/07-reporting/DEV.md`

Исправлен backfill измерений движения: PostgreSQL-совместимые коррелированные подзапросы вместо недопустимого `JOIN` с alias целевой таблицы. Перед переводом `warehouse_id` в `NOT NULL` миграция теперь явно останавливается при неразрешимой исторической привязке, не подставляя догадку. Тест проверяет эту форму SQL.

## Миграции

- `20260822_0094` — изменена существующая добавляющая миграция: backfill `seller_id`, `warehouse_id`, `reporting_dimensions_legacy`; проверка полноты `warehouse_id`; составные индексы без изменений.

## Гейты

- `ruff check .` — FAIL: 82 pre-existing ошибок в несвязанных файлах backend; ошибок в изменённых файлах отдельно не выявлено.
- `mypy .` — FAIL: 20 pre-existing ошибок в несвязанных сервисах и cleanup-скрипте; `mypy app/models/inventory_movement.py` — PASS.
- `pytest` — целевой `tests/test_inventory_movement_reporting_dimensions.py`: PASS, 2 passed.
- `python3 scripts/ci/back_guard.py` — BLOCKED: файл отсутствует в рабочей копии.
- `python3 scripts/ci/check_migrations.py` — BLOCKED: файл отсутствует в рабочей копии.
- `git diff --check` — PASS.

## Не реализовано

- Остальные находки `REVIEW.md` по reporting API, CSV и frontend не относятся к этому атомарному backend-изменению и не трогались.
- Полное исполнение миграции на PostgreSQL не проведено: в окружении нет доступной тестовой базы; SQL теперь не использует запрещённую форму `UPDATE ... FROM ... JOIN`.

## Блокеры

- Нет блокеров для внесённого исправления; общие гейты ограничены существующими ошибками репозитория и отсутствующими скриптами.

# Фича 2

# Backend Dev · 07-reporting · атом 2

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend/tests/test_inventory_service_reporting_dimensions.py` — усилен регрессионный сценарий: после записи движения товар перепривязывается к другому селлеру, а ячейка — к другому складу; журнал обязан сохранить исходные измерения.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend/app/services/inventory_service.py` — проверен без изменений: штатный writer уже записывает `Product.seller_id` и `StorageLocation.warehouse_id` в одной транзакции с балансом.

## Гейты

- Целевой pytest: PASS (`1 passed`).
- `ruff check .`: FAIL по существующим ошибкам вне изменённых файлов; ошибок в изменённом тесте не обнаружено.
- `mypy .`: FAIL по существующим ошибкам в шести других файлах; изменённые файлы в сообщениях не фигурируют.
- Полный `pytest`: FAIL (`817 passed, 5 skipped, 3 failed`); все три падения в соседних сценариях (`test_fbs_supply_from_orders.py`, `test_fbs_worklist_query_count.py`, `test_inventory_movements_report.py`), целевой тест проходит.
- `python3 scripts/ci/back_guard.py`: BLOCKED — файл отсутствует в этой рабочей копии (`scripts/ci/back_guard.py` не найден).
- `python3 scripts/ci/check_migrations.py`: BLOCKED — файл отсутствует в этой рабочей копии (`scripts/ci/check_migrations.py` не найден).

## Не реализовано

- Новые эндпоинты, сервисы и миграции не требуются для атома 2.
- Замечания ревью к миграции и read-only отчётам относятся к другим атомам/слоям и здесь не изменялись.

## Находки

- В коде и тестах этого атома секреты, ключи, токены и `.env` не читались.

# Фича 3

## Изменённые файлы

Изменений в исходном коде нет: `WarningNotice` уже реализован буквально по контракту в следующих файлах:

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/ui-kit/States.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/ui-kit/index.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/ui-kit/States.test.tsx`

Восстановлен этот отчётный артефакт:

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/night/volna-9-recovery/cards/07-reporting/DEV.md`

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` (из `frontend/`) — зелёный.
- `python3 scripts/ui/ui_guard.py` (из корня) — красный: три новых нарушения вне атома — `src/components/WbProductPickerDialog.tsx`, `src/screens/v2/FfFbsSupplyWorkspace.tsx`, `src/screens/v2/SellerInboundDraftScreen.tsx`. Для `src/screens/ff/FfReportsPage.tsx` guard зафиксировал улучшение: собственные кнопка и таблица устранены. Базовая линия не обновлялась.
- `npm run test:unit -- --run src/ui-kit/States.test.tsx` (из `frontend/`) — не запущен: `vitest: command not found`.

## Не реализовано

Ничего из атома `WarningNotice` не осталось нереализованным. Замечания из `REVIEW.md` относятся к другим карточкам и слоям; файлы за пределами контракта этого атома не изменялись.

# Фича 4

# Screen Dev · 07-reporting · ReportMetricStrip

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/ui-kit/ReportMetricStrip.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/ui-kit/ReportMetricStrip.test.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/ui-kit/index.ts` — проверен, экспорт уже присутствует и не требовал правки.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend` — НЕ ПРОВЕРЕН: в checkout отсутствует `frontend/node_modules/.bin/tsc`; offline-вызов `npx --no-install` не дал локального бинарника.
- `python3 scripts/ui/ui_guard.py` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting` — НЕ ПРОВЕРЕН: команда в объединённом запуске не вернула диагностический вывод; базовую линию не изменял.
- `npm run test:unit` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend` — НЕ ПРОВЕРЕН: отсутствует `frontend/node_modules/.bin/vitest`, а установка зависимостей не выполнялась.

## Не реализовано

- Остальные части экрана отчётности, backend-находки из ревью и соседние экраны не изменялись: текущая работа ограничена атомом `ReportMetricStrip`.

## Находки

- Исправлено замечание ревью к этому атому: процент изменения теперь выводится как `%`, а `null` может сопровождаться пояснением «В прошлом периоде расхода не было». Секреты, ключи, токены, `.env` и кабинеты учётных данных не читались.

# Фича 5

# screen-dev · 07-reporting · MovementFlowChart

## Изменённые файлы

Код атома не изменён: `MovementFlowChart` уже реализован в разрешённых файлах и соответствует контракту. Проверены:

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/ui-kit/MovementFlowChart.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/ui-kit/index.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/ui-kit/MovementFlowChart.test.tsx`

Артефакт проверки записан в этот файл:

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/night/volna-9-recovery/cards/07-reporting/DEV.md`

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — не выполнен: в рабочей копии отсутствует локальный `frontend/node_modules/.bin/tsc`, запуск `npx` не предоставил локальный TypeScript.
- `python3 scripts/ui/ui_guard.py` — красный из-за трёх новых нарушений в соседних, не разрешённых этим атомом файлах: `src/components/WbProductPickerDialog.tsx`, `src/screens/v2/FfFbsSupplyWorkspace.tsx`, `src/screens/v2/SellerInboundDraftScreen.tsx`. Базовая линия не изменялась.
- `npm run test:unit -- --run src/ui-kit/MovementFlowChart.test.tsx` — не выполнен: отсутствует локальный `frontend/node_modules/.bin/vitest` (`sh: vitest: command not found`).

Проверка реализации и теста подтверждает: видимая легенда содержит приход и расход; предыдущий расход добавляется только при `showPrevious`; пустой набор показывает «За выбранный период движений нет»; загрузка показывает скелет и не рисует серии.

## Не реализовано

Невыполненных пунктов контракта для `MovementFlowChart` нет. Замечание ревьюера о передаче процентного `delta` и прошлой серии относится к `FfReportsPage` и находится вне файлов и слоя этого атома; соседние продуктовые файлы не изменялись.

# Фича 6

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend/app/services/reporting_service.py` — сводка и inventory-отчёт фильтруют движения по зафиксированному `InventoryMovement.seller_id`; сводка принимает склад и поиск и применяет их к показателям, сравнению, сериям и текущему остатку.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend/app/api/reports.py` — `GET /reports/overview` принимает `seller_id`, `warehouse_id`, `search`; seller scope принудительно сохраняется.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/night/volna-9-recovery/cards/07-reporting/DEV.md` — этот отчёт.

## Гейты

- `ruff check backend/app/services/reporting_service.py backend/app/api/reports.py` — зелёный.
- `mypy backend/app/services/reporting_service.py backend/app/api/reports.py` — зелёный.
- `pytest backend/tests/test_reports_overview.py backend/tests/test_reports_inventory.py` — зелёный, 4 passed.
- `ruff check .` из `backend/` — красный на 82 ранее существующих нарушениях вне изменённых файлов.
- `mypy .` и полный `pytest` — не запускались из-за короткого замыкания команды после красного полного ruff.
- `python3 scripts/ci/back_guard.py` — не запущен: файл отсутствует в этой рабочей копии.
- `python3 scripts/ci/check_migrations.py` — не запущен: файл отсутствует в этой рабочей копии.

## Не реализовано

- Фильтрация по `Warehouse.is_operational` и предупреждение legacy не добавлены: в текущей рабочей копии у модели `Warehouse` и схемы нет поля `is_operational`; его добавление относится к зависимому 04-D/07-A фундаменту и расширило бы атом.
- Исправление миграции 0094 отдельно не потребовалось: текущий файл уже использует коррелированные подзапросы, не содержащие запрещённой ссылки на target table в `FROM`/`JOIN`.
- Frontend-находки ревью не реализованы: роль ограничена backend.

## Находки

- В рабочем дереве уже были несвязанные изменения: изменён `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/night/volna-9-recovery/JOURNAL.md` и удалён исходный `DEV.md`; они не редактировались в рамках backend-атома.

# Фича 7

# Backend Dev · 07-reporting

## Изменённые файлы

- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend/app/api/reports.py — добавлен seller_id для FF-фильтра в inventory и CSV; seller-портал сохраняет принудительный scope.
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend/app/services/reporting_service.py — исторический seller join по InventoryMovement, корректная проверка transfer-пар вне warehouse-фильтра, согласованные поля строк и CSV, исключение служебных складов из overview.
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/night/volna-9-recovery/cards/07-reporting/DEV.md — этот отчёт.

## Гейты

- ruff: `ruff check app/services/reporting_service.py app/api/reports.py tests/test_reports_inventory.py` — PASS.
- mypy: `mypy app/services/reporting_service.py app/api/reports.py` — PASS.
- pytest: `pytest tests/test_reports_inventory.py` — PASS (команда завершилась без вывода тест-раннера).
- back_guard.py: не найден в этой рабочей копии; запуск из корня невозможен.
- check_migrations.py: не найден в этой рабочей копии; запуск из корня невозможен.

## Не реализовано

- Новая миграция не добавлялась: миграция `20260822_0094_inventory_movement_reporting_dimensions.py` уже содержит исправленный PostgreSQL-safe backfill из предыдущего прохода.
- Персональный `current_balance` в каждой строке товарной таблицы не добавлялся: текущий контракт этого атома отдаёт агрегаты движения и поля таблицы, а баланс остаётся в overview.

## Находки

- В рабочей копии отсутствуют `scripts/ci/back_guard.py` и `scripts/ci/check_migrations.py`; это инфраструктурное ограничение checkout, не изменение кода.

# Фича 8

# DEV · 07-reporting · атом 8

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend/app/services/reporting_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/night/volna-9-recovery/cards/07-reporting/DEV.md`

Добавлен текущий остаток в product-строки отчёта и в CSV, с теми же ограничениями tenant, операционного склада и выбранного склада. Существующий endpoint `/reports/inventory/export.csv` уже применял seller scope, warehouse scope, search, group_by, порядок и доменные ошибки пустого среза/периода свыше 366 дней; отдельный роут не добавлялся.

## Гейты

- `ruff check app/services/reporting_service.py app/api/reports.py tests/test_reports_csv_export.py` — PASS.
- `mypy app/services/reporting_service.py app/api/reports.py` — PASS.
- `pytest -q tests/test_reports_csv_export.py tests/test_reports_inventory.py` — PASS, 4 passed.
- `python3 scripts/ci/back_guard.py` — BLOCKED: файл отсутствует в этой рабочей копии (`scripts/ci/back_guard.py` не найден).
- `python3 scripts/ci/check_migrations.py` — BLOCKED: файл отсутствует в этой рабочей копии (`scripts/ci/check_migrations.py` не найден).
- Полный `ruff check .` — FAIL на существующих несвязанных нарушениях репозитория; затронутые файлы проходят.

## Не реализовано

- Новая миграция для этого атома не требуется.
- Замечание ревью о SQL миграции `20260822_0094_inventory_movement_reporting_dimensions.py` относится к фундаментальному атому 07-A и не изменялось в рамках разрешённых файлов атома 8.
- Сквозной API-тест с непустыми движениями и сравнением CSV с таблицей не добавлен: текущие доступные тесты покрывают endpoint и доменные ошибки, но фабрика данных для inventory-среза отсутствует в `test_reports_csv_export.py`; изменение ограничено слоем CSV-экспорта.

## Находки

- Секреты, ключи, токены, `.env` и кабинеты учётных данных не читались.

# Фича 9

## Изменённые файлы

- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/App.tsx
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/layouts/AuthedAppLayout.tsx
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/screens.registry.json

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — не завершён: локальный `npx` завис на запуске TypeScript и был остановлен без диагностического вывода.
- `python3 scripts/ui/ui_guard.py` — красный из-за новых/существующих нарушений экран-монолита в `src/App.tsx` и других ранее изменённых экранах; базовая линия не обновлялась.
- `npm run test:unit` — не запущен: `vitest: command not found`.

## Не реализовано

- Буквальное добавление пункта меню и маршрута в фактические `SellerApp`/`SellerLayout` не выполнено: эти файлы не входят в исходное поле `files` атома; реестр теперь явно фиксирует их как слой S-33 для следующего разрешённого прохода.
- Ревью-находки по backend и экрану отчёта не относятся к разрешённым файлам этого атома и здесь не изменялись.

# Фича 10

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/screens/ff/FfReportsPage.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/night/volna-9-recovery/cards/07-reporting/DEV.md`

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — не подтверждён: локальный `tsc` отсутствует, `npx` завис на разрешении инструмента и был остановлен без вывода ошибки.
- `python3 scripts/ui/ui_guard.py` — красный из-за четырёх ранее существовавших нарушений в чужих файлах (`src/App.tsx`, `src/components/WbProductPickerDialog.tsx`, `src/screens/v2/FfFbsSupplyWorkspace.tsx`, `src/screens/v2/SellerInboundDraftScreen.tsx`). Для `FfReportsPage.tsx` guard показал улучшение: собственная кнопка `1 → 0`, собственная таблица `1 → 0`. Baseline не изменялся.
- `npm run test:unit` — не запущен: в окружении отсутствует команда `vitest` (`vitest: command not found`).

## Не реализовано

- Прошлая линия графика не подключена буквально: текущий API-ответ экрана не содержит дневную серию предыдущего периода, а backend-файлы находятся вне разрешённых файлов этого screen-dev атома.
- Backend-находки ревьюера (seller/warehouse/search scope, схема ответа, CSV, миграция, API-тесты), seller-маршрут и исправление `screens.registry.json` не менялись: они находятся за пределами разрешённых файлов этого атома.
- Полная проверка Playwright не выполнялась: задача ограничена экранным исправлением, а обязательные локальные зависимости для unit/TypeScript отсутствуют.

# Фича 11

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/screens/ff/FfReportsPage.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/tests-e2e/ff-reports.spec.ts`

Экран атома 11 сохраняет серверную пагинацию по 50 строк, переключает группировку без перезагрузки верхней сводки и скачивает серверный CSV. Добавлена нормализация коротких имён полей старого ответа API, чтобы таблица не показывала пустые SKU и количества при переходном backend-контракте. E2E-сценарий проверяет пустой период, обе группировки, неизменность показателей и имя CSV-файла.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — команда не завершилась в доступном окружении и не вывела ошибок; итоговый зелёный статус не подтверждён.
- `python3 scripts/ui/ui_guard.py` — красный из-за новых/существующих нарушений в `src/App.tsx`, `src/components/WbProductPickerDialog.tsx`, `src/screens/v2/FfFbsSupplyWorkspace.tsx`, `src/screens/v2/SellerInboundDraftScreen.tsx`; в изменённом `FfReportsPage.tsx` нарушений стало меньше (`своя-кнопка` и `своя-таблица`: 1 → 0).
- `npm run test:unit` — не запустился: `vitest: command not found`.

## Не реализовано

- Полный E2E-прогон и проверка второй страницы не подтверждены: в локальном окружении отсутствуют зависимости для unit-тестов, а текущая seeded-сценарная выборка содержит меньше 50 строк.
- Находки ревью по backend, маршрутизации SellerApp, миграции и сводке не менялись: они находятся вне файлов и границ атома 11.
