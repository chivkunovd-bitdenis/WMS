# Фича 1

# Backend-dev · 07-reporting · атом 1 · rework

## Что реализовано

- Эндпоинты: новых и изменённых эндпоинтов нет.
- Сервисы: новых и изменённых сервисов нет.
- Тестовый writer движений: `_insert_movement` принимает обязательный фактический `warehouse_id`, сохраняет его в `InventoryMovement`, а сценарий передаёт `wid1` для движений ячеек `A1`/`A2` и `wid2` для движения ячейки `B1`.

## Миграции

Нет.

## Тесты

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend/tests/test_inventory_movements_report.py` — существующий сценарий `test_inventory_movements_summary_groups_and_period_filter` теперь создаёт все движения с обязательным складом, проходит без `NOT NULL constraint failed: inventory_movements.warehouse_id` и сохраняет проверку фильтра `warehouse_id=wid1`, исключающего движение склада `wid2`.
- В том же файле уточнена типизация helper `_group` и удалены две неиспользуемые директивы `noqa`, чтобы адресные `ruff` и `mypy` были зелёными.

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend/tests/test_inventory_movements_report.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/night/volna-9-recovery/cards/07-reporting/DEV.md`

## Гейты

- ЗЕЛЁНЫЙ: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend && ruff check tests/test_inventory_movements_report.py` — `All checks passed!`, код завершения 0.
- ЗЕЛЁНЫЙ: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend && mypy tests/test_inventory_movements_report.py` — `Success: no issues found in 1 source file`, код завершения 0.
- ЗЕЛЁНЫЙ: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend && pytest tests/test_inventory_movements_report.py` — собрано 2 теста, `2 passed in 3.16s`, код завершения 0.
- `python3 scripts/ci/back_guard.py` не запускался: атом не добавляет и не меняет роуты.
- `python3 scripts/ci/check_migrations.py` не запускался: атом не добавляет миграцию.
- Полные `pytest`/`pytest -q` без путей, `ruff check .` и `mypy .` не запускались: условия атома прямо запрещают полный backend-регресс на этом шаге.

## Не реализовано

- Нет: пункт текущего атома реализован буквально.
- Находки 2–5 из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/night/volna-9-recovery/cards/07-reporting/REVIEW.md` относятся к другим атомам и слоям; они намеренно не затрагивались.

## Блокеры

Нет.

## Находки

Секреты, ключи, токены, `.env`, кабинеты учётных данных, production `194.87.96.144` и живой кабинет Wildberries не читались и не затрагивались.

# Фича 2

# Backend-dev · 07-reporting · атом 2 · rework

## Что реализовано

- Эндпоинты: новых и изменённых эндпоинтов нет; существующий `GET /reports/inventory/export.csv` сохраняет контракт маршрута и параметров.
- Сервис `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend/app/services/reporting_service.py`: таблица и CSV используют одну проверку целостности transfer-пары; в CSV неполная операция получает явную пометку `(Ошибка)`, отсутствующая сторона выводится тире, а фактически записанная сторона и нетто сохраняются без достраивания.
- Сервис `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend/app/services/reporting_service.py`: полная transfer-пара, обычные операции, сортировка и порядок строк продолжают выгружаться прежними значениями.

## Миграции

Нет.

## Тесты

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend/tests/test_reports_csv_export.py`: добавлен `test_inventory_csv_marks_incomplete_transfer_like_visible_table` (`S-33-TC-013`) — единственный `stock_transfer_out = 3` в выбранном складе имеет `integrity_error=true` в таблице, а CSV содержит `Перемещение: ушло (Ошибка),—,3,-3` и не содержит обычную строку `Перемещение: ушло,0,3,-3`.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend/tests/test_reports_csv_export.py`: добавлен `test_inventory_csv_keeps_complete_transfer_values_unchanged` (`S-33-TC-004`) — полная межскладская пара не получает ложную ошибку, и CSV повторяет значения таблицы.
- В том же адресном файле сохранён и пройден `test_inventory_csv_matches_table_grouping_and_requested_order`, который проверяет неизменность обычных операций и их порядка.
- Адресно пройден существующий регрессионный кейс `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend/tests/test_reports_inventory.py::test_reports_inventory_hides_transfers_without_warehouse_and_flags_incomplete_pair`, поскольку общая проверка transfer-пары вынесена из табличной read-модели.

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend/app/services/reporting_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend/tests/test_reports_csv_export.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/night/volna-9-recovery/cards/07-reporting/DEV.md`

## Гейты

- ИСХОДНО КРАСНЫЙ, ИСПРАВЛЕНО: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend && ruff check app/services/reporting_service.py tests/test_reports_csv_export.py` — найден один `E501` в новой тестовой строке, код завершения 1; строка разбита без изменения поведения.
- ЗЕЛЁНЫЙ: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend && ruff check app/services/reporting_service.py tests/test_reports_csv_export.py` — `All checks passed!`, код завершения 0.
- ЗЕЛЁНЫЙ: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend && mypy app/services/reporting_service.py tests/test_reports_csv_export.py` — `Success: no issues found in 2 source files`, код завершения 0; команда повторно прошла после последней форматной правки с тем же результатом.
- ЗЕЛЁНЫЙ: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend && pytest -q tests/test_reports_csv_export.py tests/test_reports_inventory.py::test_reports_inventory_hides_transfers_without_warehouse_and_flags_incomplete_pair` — `9 passed in 11.18s`, код завершения 0.
- `python3 scripts/ci/back_guard.py` не запускался: атом не добавляет и не меняет роуты.
- `python3 scripts/ci/check_migrations.py` не запускался: атом не добавляет миграцию.
- Полные `pytest`/`pytest -q` без путей, `ruff check .` и `mypy .` не запускались: условия атома прямо запрещают полный backend-регресс на этом шаге.

## Не реализовано

- Нет: находка №2 из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/night/volna-9-recovery/cards/07-reporting/REVIEW.md` и текущий атом реализованы буквально.
- Находки №1 и №3–5 относятся к другим атомам и файлам; в этом шаге они намеренно не затрагивались.

## Блокеры

Нет.

## Находки

Секреты, ключи, токены, `.env`, кабинеты учётных данных, production `194.87.96.144` и живой кабинет Wildberries не читались и не затрагивались.

# Фича 3

# Backend-dev · 07-reporting · атом 3 · rework

## Что реализовано

- Эндпоинты: существующие `GET /warehouses`, `POST /warehouses` и `PATCH /warehouses/{warehouse_id}` возвращают авторитетный булев признак `is_operational` из модели склада; создание даёт штатное `true`, а переименование не меняет признак, `id`, `code` и остальные поля ответа.
- Сервисы: изменений нет; существующие `list_warehouses`, `create_warehouse` и `rename_warehouse` уже сохраняют модельный признак без эвристики по имени.

## Миграции

Нет: поле `Warehouse.is_operational` уже существует и является обязательным булевым полем с default `true`.

## Тесты

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend/tests/test_catalog.py::test_catalog_flow` — создание обычного склада и последующий `GET /warehouses` проверяют явное булево `is_operational: true`.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend/tests/test_catalog.py::test_warehouse_read_model_preserves_operational_flag_after_rename` — неоперационный служебный склад переименовывается из `FBS WB Service` в `Archive`; `PATCH` и повторный `GET /warehouses` сохраняют `is_operational: false`, `id` и `code`.

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend/app/api/warehouses.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend/tests/test_catalog.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/night/volna-9-recovery/cards/07-reporting/DEV.md`

## Гейты

- ЗЕЛЁНЫЙ: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend && ruff check app/api/warehouses.py tests/test_catalog.py` — `All checks passed!`, код завершения 0.
- ИСХОДНО КРАСНЫЙ ВНЕ АТОМА: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend && mypy app/api/warehouses.py tests/test_catalog.py` — обход импортов нашёл 4 существующие ошибки в `wildberries_credentials_service.py`, `fbs_stock_sync_service.py` и `fbs_warehouse_binding_service.py`; изменённые файлы в списке ошибок отсутствуют, код завершения 1.
- НЕ ИСПОЛЬЗОВАН КАК ИТОГОВЫЙ ГЕЙТ: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend && mypy --follow-imports=skip app/api/warehouses.py tests/test_catalog.py` — режим `skip` лишил импортированные библиотеки типов и дал 26 ложных ошибок `Any` в двух целевых файлах, код завершения 1.
- ЗЕЛЁНЫЙ: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend && mypy --follow-imports=silent app/api/warehouses.py tests/test_catalog.py` — `Success: no issues found in 2 source files`, код завершения 0; импортированные модули используются для типизации, но их посторонние ошибки не включены в результат атома.
- ЗЕЛЁНЫЙ: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend && pytest -q tests/test_catalog.py` — `7 passed in 8.13s`, код завершения 0.
- `python3 scripts/ci/back_guard.py` не запускался: новый роут не добавлялся, изменён только ответ существующих маршрутов.
- `python3 scripts/ci/check_migrations.py` не запускался: миграция не добавлялась.
- Полные `pytest`/`pytest -q` без путей, `ruff check .` и `mypy .` не запускались: условия атома прямо запрещают полный backend-регресс на этом шаге.

## Не реализовано

- Нет: находка №4 из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/night/volna-9-recovery/cards/07-reporting/REVIEW.md` в части backend API и текущий атом реализованы буквально.
- Frontend-фильтрация из атомов 4 и 5, исправление загрузки из атома 6 и реестр блокировки из атома 7 намеренно не затрагивались: это соседние продуктовые задачи и не роль `backend-dev`.

## Блокеры

- Реализация и целевые проверки завершены, но сохранить атом в Git из текущего sandbox невозможно: команда `git add backend/app/api/warehouses.py backend/tests/test_catalog.py night/volna-9-recovery/cards/07-reporting/DEV.md && git commit -m "fix(warehouses): expose operational flag"` не смогла создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-1-07-reporting1/index.lock` и завершилась с `Operation not permitted`. Изменения остаются в рабочем дереве без commit SHA; чужой `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/night/volna-9-recovery/JOURNAL.md` не индексировался и не изменялся этой ролью.

## Находки

- Обычный адресный `mypy` проходит по импортам и видит четыре существующие ошибки в трёх чужих сервисах; итоговая проверка целевых модулей выполнена с `--follow-imports=silent`.
- Секреты, ключи, токены, `.env`, кабинеты учётных данных, production `194.87.96.144` и живой кабинет Wildberries не читались и не затрагивались.

# Фича 4

# Screen-dev · 07-reporting · атом 4 · rework

## Что реализовано

- Тип склада в клиенте теперь требует обязательный булев признак `is_operational`, который публикует уже выполненный атом 3.
- В отчёт ФФ передаются только склады с `is_operational=true`; эвристика по префиксу `FBS WB ` удалена.
- Playwright-сценарий `S-33-TC-003 / S-33-TC-014` подменяет `/api/warehouses` ровно двумя складами: одним операционным и переименованным `Архив` с `is_operational=false`; проверяет, что `Архив` не доступен, а селектор одного оставшегося склада скрыт.

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/App.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/tests-e2e/ff-reports.spec.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/night/volna-9-recovery/cards/07-reporting/DEV.md`

## Гейты

- **ЗЕЛЁНЫЙ:** `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend && npx tsc --noEmit -p tsconfig.app.json` — код завершения 0.
- **КРАСНЫЙ ИЗ-ЗА НАКОПЛЕННОГО СОСТОЯНИЯ ВЕТКИ:** `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting && python3 scripts/ui/ui_guard.py` — код завершения 1. Сторож показал уже существовавшие до атома превышения общей baseline: `src/App.tsx: экран-монолит 3492 → 3511`, `src/components/WbProductPickerDialog.tsx: 0 → 646`, `src/screens/v2/FfFbsSupplyWorkspace.tsx: 2493 → 2498`, `src/screens/v2/SellerInboundDraftScreen.tsx: 1111 → 1169`. Текущий diff атома не добавляет строк в `App.tsx`: и в `HEAD`, и после правки файл имеет 3510 строк по `wc -l`. Три других файла не входят в границы атома. Baseline флагом `--update` не двигалась.
- **ЗЕЛЁНЫЙ:** `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend && npm run test:unit -- src/screens/ff/FfReportsPage.test.tsx` — 1 файл, 1 тест, `1 passed`, код завершения 0.
- **КРАСНЫЙ ИЗ-ЗА ОГРАНИЧЕНИЯ СРЕДЫ:** `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend && npx playwright test tests-e2e/ff-reports.spec.ts --grep "FF reports exclude non-operational warehouses from the warehouse filter"` — Playwright не дошёл до браузерного теста: тестовый API не смог открыть `127.0.0.1:18000`, `Errno 1: operation not permitted`; код завершения 1.
- **ЗЕЛЁНЫЙ, обнаружение и компиляция сценария без webServer:** `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend && npx playwright test tests-e2e/ff-reports.spec.ts --grep "FF reports exclude non-operational warehouses from the warehouse filter" --list` — найден 1 тест в 1 файле, код завершения 0.
- **ЗЕЛЁНЫЙ:** `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting && git diff --check` — ошибок формата diff нет, код завершения 0.
- Полные backend-прогоны и полный Playwright не запускались: текущий шаг разрешает только атомарную проверку.

## Не реализовано

- Пунктов контракта, не получивших буквальной реализации в границах атома 4, нет.
- Не завершена только живая браузерная проверка: sandbox запретил поднять локальный API. Сценарий обнаруживается и компилируется, но фактический клик и проверка DOM в этом проходе не состоялись.

## Находки

- Новых находок по данным или видимому поведению в границах атома нет.
- Секреты, ключи, токены, `.env`, кабинеты учётных данных, production `194.87.96.144` и живой кабинет Wildberries не читались и не затрагивались.

# Фича 5

# Screen-dev · 07-reporting · атом 5 · rework

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/apps/seller/SellerApp.tsx` — `is_operational` сделан обязательной частью ответа склада; отчёт селлера больше не угадывает назначение склада по имени и принимает только строки с `is_operational=true`.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/apps/seller/SellerApp.test.tsx` — адресный unit-тест закрепляет, что переименованный `Архив` исключается по API-признаку, а имя с префиксом `FBS WB` само по себе не исключает операционный склад.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/tests-e2e/seller-reports.spec.ts` — сценарий `S-33-TC-003 / S-33-TC-014` возвращает один операционный склад и переименованный неоперационный `Архив`, создаёт движения двух селлеров в одном tenant и проверяет скрытие складского и селлерского фильтров, отсутствие `Архива` и отсутствие SKU другого селлера в таблице.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/night/volna-9-recovery/cards/07-reporting/DEV.md` — отчёт текущей роли.

## Гейты

- **ЗЕЛЁНЫЙ:** `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend && npx tsc --noEmit -p tsconfig.app.json` — код завершения 0.
- **КРАСНЫЙ ИЗ-ЗА НАКОПЛЕННОГО СОСТОЯНИЯ ВЕТКИ:** `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting && python3 scripts/ui/ui_guard.py` — код завершения 1. Сторож показал уже существующие превышения baseline в `src/App.tsx` (`3492 → 3511`), `src/components/WbProductPickerDialog.tsx` (`0 → 646`), `src/screens/v2/FfFbsSupplyWorkspace.tsx` (`2493 → 2498`) и `src/screens/v2/SellerInboundDraftScreen.tsx` (`1111 → 1169`). Текущий атом не меняет эти файлы; `SellerApp.tsx` остался длиной 542 строки до и после правки. Baseline флагом `--update` не менялась.
- **ЗЕЛЁНЫЙ:** `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend && npm run test:unit -- src/apps/seller/SellerApp.test.tsx` — 1 файл, 2 теста, `2 passed`, код завершения 0.
- **КРАСНЫЙ ИЗ-ЗА ОГРАНИЧЕНИЯ СРЕДЫ:** `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend && npx playwright test tests-e2e/seller-reports.spec.ts --grep "seller reports exclude non-operational warehouses and other seller data"` — Playwright не дошёл до сценария: тестовый API не смог открыть `127.0.0.1:18000`, `Errno 1: operation not permitted`; код завершения 1.
- **ЗЕЛЁНЫЙ, обнаружение и компиляция сценария без webServer:** `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend && npx playwright test tests-e2e/seller-reports.spec.ts --grep "seller reports exclude non-operational warehouses and other seller data" --list` — найден ровно 1 тест в 1 файле, код завершения 0.
- **ЗЕЛЁНЫЙ:** `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting && git diff --check` — ошибок формата diff нет, код завершения 0.
- Полный backend-регресс, полный Playwright, `ruff check .` и `mypy .` не запускались: условия атома прямо запрещают эти команды на текущем шаге.

## Не реализовано

- Пунктов контракта, не реализованных буквально в коде атома 5, нет.
- Живая браузерная проверка не состоялась: sandbox запрещает тестовому API открыть локальный порт. Сценарий обнаруживается и компилируется, но реальные действия браузера и проверка DOM в этом проходе не выполнялись.

## Блокеры

- Локальная реализация не сохранена в Git commit: команда `git add frontend/src/apps/seller/SellerApp.tsx frontend/src/apps/seller/SellerApp.test.tsx frontend/tests-e2e/seller-reports.spec.ts night/volna-9-recovery/cards/07-reporting/DEV.md && git diff --cached --check && git diff --cached --stat && git commit -m "fix(reports): filter seller warehouses by operational flag"` не смогла создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-1-07-reporting1/index.lock` и завершилась с `Operation not permitted`. Изменения остаются в рабочем дереве без commit SHA. Чужой `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/night/volna-9-recovery/JOURNAL.md` не индексировался и не изменялся этой ролью.

## Находки

- Новых находок по данным, утечкам, секретам или персональным данным в границах атома нет.
- Секреты, ключи, токены, `.env`, кабинеты учётных данных, production `194.87.96.144` и живой кабинет Wildberries не читались и не затрагивались.

# Фича 6

# Screen-dev · 07-reporting · атом 6 · rework

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/screens/ff/FfReportsPage.tsx` — при смене фильтров отменённый запрос отдельной страницы больше не оставляет `tableLoading=true`; новый срез после загрузки снимает табличный скелетон, а отменённый контроллер остаётся отвязанным и не может записать поздний ответ.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/tests-e2e/ff-reports.spec.ts` — сценарий `S-33-TC-008` теперь буквально проверяет отсутствие строк скелетона после появления `Fresh filtered result`; проверки отсутствия `Stale page result` после освобождения старого ответа сохранены.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/night/volna-9-recovery/cards/07-reporting/DEV.md` — отчёт текущего атома.

## Гейты

- **ЗЕЛЁНЫЙ:** `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend && npx tsc --noEmit -p tsconfig.app.json` — код завершения 0.
- **КРАСНЫЙ ИЗ-ЗА НАКОПЛЕННОГО СОСТОЯНИЯ ВЕТКИ:** `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting && python3 scripts/ui/ui_guard.py` — код завершения 1. Сторож отметил улучшения целевого экрана (`FfReportsPage.tsx`: `своя-кнопка 1 → 0`, `своя-таблица 1 → 0`), но показал уже существующие превышения baseline вне файлов атома: `src/App.tsx: экран-монолит 3492 → 3511`, `src/components/WbProductPickerDialog.tsx: 0 → 646`, `src/screens/v2/FfFbsSupplyWorkspace.tsx: 2493 → 2498`, `src/screens/v2/SellerInboundDraftScreen.tsx: 1111 → 1169`. Baseline флагом `--update` не менялась, чужие файлы не правились.
- **ЗЕЛЁНЫЙ:** `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend && npm run test:unit -- src/screens/ff/FfReportsPage.test.tsx` — 1 файл, 1 тест, `1 passed`, код завершения 0.
- **КРАСНЫЙ ИЗ-ЗА ОГРАНИЧЕНИЯ СРЕДЫ:** `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend && npx playwright test tests-e2e/ff-reports.spec.ts --grep "FF report keeps one table slice and distinguishes a table error from empty data"` — команда выполнена до и после правки; оба раза Playwright не дошёл до браузерного сценария, потому что тестовый API не смог открыть `127.0.0.1:18000` (`Errno 1: operation not permitted`), код завершения 1.
- **ЗЕЛЁНЫЙ, ОБНАРУЖЕНИЕ И КОМПИЛЯЦИЯ СЦЕНАРИЯ:** `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend && npx playwright test tests-e2e/ff-reports.spec.ts --grep "FF report keeps one table slice and distinguishes a table error from empty data" --list` — найден ровно 1 тест в 1 файле, код завершения 0.
- **ЗЕЛЁНЫЙ:** `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting && git diff --check` — ошибок формата diff нет, код завершения 0.
- **КРАСНЫЙ ИЗ-ЗА ОГРАНИЧЕНИЯ GIT-МЕТАДАННЫХ:** `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting && git add frontend/src/screens/ff/FfReportsPage.tsx frontend/tests-e2e/ff-reports.spec.ts night/volna-9-recovery/cards/07-reporting/DEV.md && git diff --cached --check && git diff --cached --stat && git commit -m "fix(reports): clear stale pagination loading"` — команда остановилась на `git add`: Git не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-1-07-reporting1/index.lock` (`Operation not permitted`), код завершения 128. Чужой `JOURNAL.md` не индексировался.
- Полный backend `pytest`, `ruff check .`, `mypy .` и полный Playwright не запускались: условия атома прямо запрещают полный регресс на этом шаге.

## Не реализовано

- Пунктов контракта или находки №3 из `REVIEW.md`, не реализованных буквально в коде атома 6, нет.
- Живое прохождение `S-33-TC-008` не состоялось из-за запрета среды на локальный порт тестового API; сценарий обнаруживается и компилируется, но фактический браузерный проход в этой рабочей копии не подтверждён.
- Изменения не сохранены в Git-коммите: sandbox разрешает менять рабочие файлы, но запрещает запись в Git-метаданные основного checkout. Commit SHA отсутствует, результат остаётся только в рабочем дереве.
- Находки №1, №2, №4 и №5 из `REVIEW.md` относятся к другим атомам и файлам; в этом шаге они намеренно не затрагивались.

## Находки

- Новых находок по данным или видимому поведению за границами атома нет.
- Секреты, ключи, токены, `.env`, кабинеты учётных данных, production `194.87.96.144` и живой кабинет Wildberries не читались и не затрагивались.

# Фича 7

# Screen-dev · 07-reporting · атом 7 · rework

Исправлена находка №5 из повторного `REVIEW.md`: ограничение доступа к S-33
зафиксировано отдельной шестипольной записью, а оба ролевых отказа получили
адресные браузерные сценарии. Остальные четыре находки относятся к другим атомам
и файлам, поэтому в этом проходе не затрагивались.

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/tests-e2e/ff-reports.spec.ts` — добавлен `S-33-TC-015`: сотрудник ФФ с правом приёмки, но без `inventory` и `cells`, открывает `/app/ff/reports` напрямую, видит «Нет доступа», не видит меню и блоки отчёта; запросы `/api/reports/*` не уходят.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/tests-e2e/seller-reports.spec.ts` — добавлен `S-33-TC-016`: сотрудник селлера с документами, но без `can_products`, открывает прямой маршрут отчёта, видит адресный отказ и не получает показатели, график или таблицу; запросы `/api/reports/*` не уходят.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/docs/blockers/S-33.md` — добавлена отдельная запись «Отчёт без права доступа» со всеми шестью обязательными полями: предмет блокировки, условие, место проверки, видимое состояние, разблокировка и бизнес-причина.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/night/volna-9-recovery/cards/07-reporting/DEV.md` — отчёт текущего атома.

## Гейты

- **ЗЕЛЁНЫЙ:** рабочий каталог `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend`; команда `npx tsc --noEmit -p tsconfig.app.json` — код завершения 0.
- **КРАСНЫЙ ИЗ-ЗА НАКОПЛЕННОГО СОСТОЯНИЯ ВЕТКИ:** рабочий каталог `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting`; команда `python3 scripts/ui/ui_guard.py` — код завершения 1. Новых нарушений в файлах атома нет; сторож повторил прежние превышения baseline в `frontend/src/App.tsx` (`экран-монолит 3492 → 3511`), `frontend/src/components/WbProductPickerDialog.tsx` (`0 → 646`), `frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx` (`2493 → 2498`) и `frontend/src/screens/v2/SellerInboundDraftScreen.tsx` (`1111 → 1169`). Для `FfReportsPage.tsx` сторож, наоборот, отметил улучшение по собственной кнопке и таблице. Baseline флагом `--update` не менялась.
- **ЗЕЛЁНЫЙ:** рабочий каталог `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend`; команда `npm run test:unit -- src/screens/ff/FfReportsPage.test.tsx src/apps/seller/SellerApp.test.tsx` — 2 файла, 3 теста, `3 passed`, код завершения 0.
- **КРАСНЫЙ ИЗ-ЗА ОГРАНИЧЕНИЯ СРЕДЫ:** рабочий каталог `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend`; команда `npx playwright test tests-e2e/ff-reports.spec.ts tests-e2e/seller-reports.spec.ts --grep "staff without (inventory|products) access cannot open the direct reports route"` — Playwright не дошёл до браузерных сценариев, потому что тестовый API не смог открыть `127.0.0.1:18000` (`Errno 1: operation not permitted`), код завершения 1.
- **ЗЕЛЁНЫЙ, ОБНАРУЖЕНИЕ И КОМПИЛЯЦИЯ СЦЕНАРИЕВ:** рабочий каталог `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend`; команда `npx playwright test tests-e2e/ff-reports.spec.ts tests-e2e/seller-reports.spec.ts --grep "staff without (inventory|products) access cannot open the direct reports route" --list` — найдены ровно 2 теста в 2 файлах, код завершения 0.
- **ЗЕЛЁНЫЙ:** рабочий каталог `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend`; команда `npx eslint tests-e2e/ff-reports.spec.ts tests-e2e/seller-reports.spec.ts` — код завершения 0.
- **ЗЕЛЁНЫЙ:** рабочий каталог `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting`; команда `python3 -c "from pathlib import Path; text=Path('docs/blockers/S-33.md').read_text(); section=text.split('### Отчёт без права доступа',1)[1].split('### Выгрузка CSV',1)[0]; fields=['Что блокируется','Каким условием','Где живёт проверка','Что видит оператор','Как разблокировать','Зачем бизнесово']; missing=[field for field in fields if f'**{field}:**' not in section]; assert not missing, missing; print('S-33 access blocker: 6/6 fields present')"` — `6/6 fields present`, код завершения 0.
- **ЗЕЛЁНЫЙ:** рабочий каталог `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting`; команда `git diff --check` — ошибок формата diff нет, код завершения 0.
- **ЗЕЛЁНЫЙ:** в именованной ветке `night/volna-9-recovery/lane-1/07-reporting` команда `git commit -m "test(reports): cover denied report routes"` создала отдельный локальный коммит только из четырёх файлов атома; чужой `night/volna-9-recovery/JOURNAL.md` в него не вошёл.
- **КРАСНЫЙ ИЗ-ЗА ОГРАНИЧЕНИЯ СЕТИ:** команда `git push -u origin HEAD` не смогла разрешить имя `github.com` (`Could not resolve host`), код завершения 128. Ветка сохранена локально, но в remote не опубликована.
- Полный backend `pytest`, `ruff check .`, `mypy .`, полный Playwright и соседние атомы не запускались: атомарная проверка прямо ограничена двумя адресными сценариями и относящимися к экрану unit-тестами.

## Не реализовано

- Живое прохождение `S-33-TC-015` и `S-33-TC-016` в этой среде не подтверждено: локальный API нельзя привязать к порту из-за sandbox-ограничения. Оба сценария обнаруживаются и компилируются Playwright, но это не заменяет браузерный проход.
- Реестр называет маршрут селлера `/app/seller/reports`, а текущая локальная Playwright-сборка отдельного `SellerApp` использует basename `/seller`; поэтому `S-33-TC-016` открывает эквивалентный прямой путь `/seller/reports` через штатный `sellerPath('/reports')`. Буквальный URL `/app/seller/reports` этой конфигурацией не обслуживается отдельным seller-приложением.
- Локальная ветка не опубликована в `origin` из-за отсутствия DNS-доступа к GitHub. Деплой и production не выполнялись.

## Находки

- Новых находок по данным, персональным данным или видимому поведению за границами атома нет.
- Секреты, ключи, токены, `.env`, кабинеты учётных данных, production `194.87.96.144` и живой кабинет Wildberries не читались и не затрагивались.
