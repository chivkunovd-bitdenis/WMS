# Фича 1

# Backend development · 07-reporting · атом 1

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend/alembic/versions/20260822_0094_inventory_movement_reporting_dimensions.py` — backfill сохраняет доступные текущие измерения, но помечает каждую исторически реконструированную строку как `reporting_dimensions_legacy`, чтобы текущая связь не была выдана за доказанный факт прошлого.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend/tests/test_inventory_movement_reporting_dimensions.py` — зафиксирован консервативный контракт legacy-backfill и индексов.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/night/volna-9-recovery/cards/07-reporting/DEV.md` — отчёт атома.

## Гейты

- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend && ruff check app/models/inventory_movement.py alembic/versions/20260822_0094_inventory_movement_reporting_dimensions.py tests/test_inventory_movement_reporting_dimensions.py` — `All checks passed!`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend && mypy app/models/inventory_movement.py` — `Success: no issues found in 1 source file`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend && pytest -q tests/test_inventory_movement_reporting_dimensions.py` — `2 passed in 0.02s`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting && python3 scripts/ci/back_guard.py` — не применён: файла `scripts/ci/back_guard.py` в этой рабочей копии нет.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting && python3 scripts/ci/check_migrations.py` — не запускался, потому что названный скрипт также отсутствует в этой рабочей копии.
- `git diff --check` — без ошибок.

## Не реализовано

- Пункты следующих атомов из `FEATURES.md` не затрагивались.
- Фактический PostgreSQL round-trip миграции не запускался: в репозитории нет требуемых CI-скриптов, а отдельный тестовый URL базы не предоставлен. Целевой тест фиксирует SQL-контракт миграции.

## Находки

- Секреты, ключи, токены, `.env` и кабинеты учётных данных не читались.

# Фича 2

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend/app/services/inventory_service.py` — общий writer уже записывает `seller_id=Product.seller_id` и `warehouse_id=StorageLocation.warehouse_id` при создании `InventoryMovement` в той же транзакции, что и изменение остатка.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend/tests/test_inventory_service_reporting_dimensions.py` — сценарий движения с последующей перепривязкой товара и ячейки подтверждает сохранение исходных измерений.

## Гейты

- `ruff check .` — FAIL: 82 существующие ошибки вне файлов атома, включая FBS-сервисы, служебные cleanup-скрипты и несвязанные тесты.
- `mypy .` — FAIL: 21 существующая ошибка в 6 несвязанных файлах; `inventory_service.py` и целевой тест в выводе ошибок отсутствуют.
- `pytest -q tests/test_inventory_service_reporting_dimensions.py` — PASS: 1 passed.
- `python3 scripts/ci/back_guard.py` — BLOCKED: файл отсутствует в рабочей копии.
- `python3 scripts/ci/check_migrations.py` — BLOCKED: файл отсутствует в рабочей копии.

## Не реализовано

- Замечания ревью 1–15 по `reporting_service.py`, API и frontend не относятся к атомарному writer-контракту и намеренно не менялись.
- Новых изменений в коде не потребовалось: требование атома уже выполнено текущей реализацией `record_movement_and_adjust_balance` и покрыто целевым тестом.
- Секреты, ключи, токены и `.env` не читались.

# Фича 3

# Screen-dev report · 07-reporting · атом 3

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/vitest.config.ts` — добавлено обнаружение `src/**/*.test.tsx`, чтобы существующий атомарный тест `WarningNotice` действительно запускался.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/night/volna-9-recovery/cards/07-reporting/DEV.md` — записан отчёт повторного прохода.

Реализация атома уже находится в разрешённых файлах `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/ui-kit/States.tsx`, `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/ui-kit/index.ts` и `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/ui-kit/States.test.tsx`; менять её для закрытия находки review не потребовалось. `WarningNotice` использует MUI `Alert` с `severity="warning"`, совпадающий с `ErrorNotice` отступ `mb: 2`, принимает `testId` и экспортируется через публичный индекс ui-kit.

## Гейты

- **ЗЕЛЁНЫЙ:** `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend && npm run test:unit -- --run src/ui-kit/States.test.tsx` — Vitest обнаружил `src/ui-kit/States.test.tsx`; 1 файл и 1 тест пройдены. Тест проверяет `data-testid`, доступную роль `alert`, warning-класс MUI и читаемый текст.
- **КРАСНЫЙ вне границы атома 3:** `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend && npx tsc --noEmit -p tsconfig.app.json` — три уже описанные в `REVIEW.md` ошибки `TS2769` в `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/ui-kit/MovementFlowChart.tsx` на строках 39, 84 и 91. Файл относится к атому 5 и не входит в разрешённые файлы атома `WarningNotice`.
- **КРАСНЫЙ вне границы атома 3:** `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting && python3 scripts/ui/ui_guard.py` — храповик сообщил о превышениях в `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/App.tsx`, `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/components/WbProductPickerDialog.tsx`, `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx` и `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/screens/v2/SellerInboundDraftScreen.tsx`. По файлам атома новых нарушений нет; baseline не изменялась.
- **КРАСНЫЙ по ограничению песочницы:** `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting && git add -- frontend/vitest.config.ts night/volna-9-recovery/cards/07-reporting/DEV.md && git diff --cached --check && git commit -m "fix(ui-kit): run WarningNotice unit test"` — Git не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-1-07-reporting1/index.lock`: `Operation not permitted`. Commit SHA отсутствует.

Полные backend `pytest`, `ruff check .` и `mypy .` не запускались согласно атомарной границе.

## Не реализовано

- В самом атоме `WarningNotice` невыполненных пунктов контракта нет.
- Общий `tsc` и `ui_guard.py` не зелёные из-за находок других атомов. Исправления `MovementFlowChart.tsx` и перечисленных экранов не выполнялись, потому что пользователь запретил переходить к следующим атомам и править соседние файлы.
- Результат локально реализован, но не сохранён отдельным Git-коммитом: песочница запрещает запись в общий Git-каталог зарегистрированного worktree.

## Находки

- Находка review №3 для `States.test.tsx` закрыта: после изменения `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/vitest.config.ts` целевой `.test.tsx` обнаруживается и проходит.
- Секреты, ключи, токены, `.env`, кабинеты учётных данных, production `194.87.96.144` и живой кабинет Wildberries не читались и не затрагивались.

# Фича 4

# Screen-dev · 07-reporting · атом 4

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/ui-kit/ReportMetricStrip.test.tsx` — тест явно проверяет подписи и значения всех четырёх зон, нулевое значение, `null` как `—` с пояснением и ровно четыре скелета без показа каждого устаревшего числа и дельты.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/night/volna-9-recovery/cards/07-reporting/DEV.md` — отчёт этого атомарного прохода.

Сам `ReportMetricStrip` и его публичный экспорт уже находятся в сохранённом `HEAD` и буквально соответствуют контракту: одна outlined-полоса, четыре равные зоны без вложенных карточек, правое выравнивание, табличные цифры, единица `шт.`, `—` для неприменимого сравнения и скелеты при загрузке. Дополнительной правки `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/ui-kit/ReportMetricStrip.tsx` и `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/ui-kit/index.ts` не потребовалось.

Находка review №3 для этого атома закрыта: текущий `HEAD` уже содержит прямо названную ревьюером правку `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/vitest.config.ts`, поэтому `.test.tsx` обнаруживается Vitest и целевой тест действительно выполняется.

## Гейты

- **ЗЕЛЁНЫЙ:** `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend && npm run test:unit -- src/ui-kit/ReportMetricStrip.test.tsx` — Vitest выполнил 1 файл, все 3 теста пройдены.
- **ЗЕЛЁНЫЙ:** `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend && npx eslint src/ui-kit/ReportMetricStrip.tsx src/ui-kit/ReportMetricStrip.test.tsx && git diff --check -- src/ui-kit/ReportMetricStrip.test.tsx` — замечаний нет.
- **КРАСНЫЙ вне границы атома 4:** `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend && npx tsc --noEmit -p tsconfig.app.json` — три ошибки `TS2769` в `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/ui-kit/MovementFlowChart.tsx` на строках 39, 84 и 91: текущие MUI-типы не принимают прямые props `alignItems`, `fontWeight` и `flexWrap`. Это находка review №2 и файл следующего атома 5; `ReportMetricStrip` в выводе ошибок отсутствует.
- **КРАСНЫЙ вне границы атома 4:** `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting && python3 scripts/ui/ui_guard.py` — храповик сообщает прежние превышения в `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/App.tsx`, `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/components/WbProductPickerDialog.tsx`, `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx` и `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/screens/v2/SellerInboundDraftScreen.tsx`. В файлах атома новых нарушений нет; baseline не обновлялась.
- **КРАСНЫЙ по ограничению песочницы:** `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting && git add -- frontend/src/ui-kit/ReportMetricStrip.test.tsx night/volna-9-recovery/cards/07-reporting/DEV.md && git diff --cached --check && git commit -m "test(ui-kit): cover report metric strip states"` — Git не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-1-07-reporting1/index.lock`: `Operation not permitted`. Отдельный commit SHA отсутствует.

Полные backend `pytest`, `ruff check .` и `mypy .` не запускались согласно атомарному ограничению пользователя.

## Не реализовано

- В самом атоме `ReportMetricStrip` невыполненных пунктов контракта нет.
- Общие `tsc` и `ui_guard.py` не зелёные из-за файлов других атомов. Они не исправлялись, потому что пользователь запретил переходить к следующим атомам и править соседние продуктовые задачи.
- Изменения локально реализованы, но не сохранены отдельным Git-коммитом: песочница запрещает запись в общий Git-каталог зарегистрированного worktree.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных, production `194.87.96.144` и живой кабинет Wildberries не читались и не затрагивались.

# Фича 5

# Screen Dev · 07-reporting · атом 5

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/ui-kit/MovementFlowChart.tsx` — несовместимые с MUI 9 прямые свойства `alignItems`, `flexWrap` и `fontWeight` перенесены в `sx`; поведение и состав графика не менялись.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/night/volna-9-recovery/cards/07-reporting/DEV.md` — записан обязательный отчёт роли.

`/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/ui-kit/index.ts` и `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/ui-kit/MovementFlowChart.test.tsx` уже соответствовали контракту и не потребовали правок. Названная ревьюером проблема обнаружения `.test.tsx` уже устранена в текущей ветке: `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/vitest.config.ts` включает `src/**/*.test.tsx`; целевой тест действительно запустился.

## Гейты

- Зелёный: из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend` выполнено `npx tsc --noEmit -p tsconfig.app.json`; код завершения 0, ошибок нет.
- Красный по изменениям вне атома: из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting` выполнено `python3 scripts/ui/ui_guard.py`; код завершения 1. Храповик сообщил новые нарушения только в `src/App.tsx` (экран-монолит 3492 → 3511), `src/components/WbProductPickerDialog.tsx` (экран-монолит 0 → 646), `src/screens/v2/FfFbsSupplyWorkspace.tsx` (экран-монолит 2493 → 2498) и `src/screens/v2/SellerInboundDraftScreen.tsx` (экран-монолит 1111 → 1169). Эти файлы не относятся к атому 5 и не входят в разрешённую область правок. Базовая линия не обновлялась.
- Зелёный: из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend` выполнено `npm run test:unit -- src/ui-kit/MovementFlowChart.test.tsx`; 1 файл и 3 теста прошли.
- Красный по ограничению песочницы: из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting` выполнено `git add -- frontend/src/ui-kit/MovementFlowChart.tsx night/volna-9-recovery/cards/07-reporting/DEV.md && git diff --cached --check && git diff --cached --stat && git commit -m "fix(ui-kit): repair movement flow chart build"`; Git не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-1-07-reporting1/index.lock` (`Operation not permitted`). Отдельный commit SHA отсутствует.

## Не реализовано

В самом контракте атома 5 отступлений нет. Общий `ui_guard.py` не удалось сделать зелёным без запрещённых правок четырёх соседних файлов, перечисленных в разделе «Гейты». Изменения локально реализованы, но не сохранены отдельным Git-коммитом: песочница запрещает запись в общий Git-каталог зарегистрированного worktree.

## Находки

Находок о данных, персональных данных или секретах в пределах этого атома нет. Секреты, ключи, токены, `.env` и кабинеты учётных данных не читались.

# Фича 6

# Backend Dev · 07-reporting · атом 6 · переделка по review

## Что реализовано

- `GET /reports/overview` — наивные границы периода теперь трактуются как московские календарные даты и переводятся в UTC; полуоткрытый интервал исключает движение ровно на верхней границе.
- `reporting_service.build_overview` — дневной ряд содержит нулевые календарные дни между фактами, внутренние transfer-движения не попадают во внешние итоги, а пустой текущий и предыдущий поток по-прежнему возвращает пустую серию.
- `reporting_service.build_overview` — свежесть Wildberries определяется по последнему успешно завершённому входящему import-job, а не по исходящей публикации остатков; более новая неуспешная попытка не выдаётся за свежие данные.
- `reporting_service.build_inventory_report` и `build_inventory_csv` — человекопонятная классификация операций переиспользована из существующего сервиса отчёта; повреждённая пара обязана содержать ровно один `stock_transfer_out` и один `stock_transfer_in`.

## Миграции

Нет.

## Тесты

- `backend/tests/test_reports_overview.py` — проверяет московскую трактовку offset-less дат, полуоткрытую верхнюю границу, нулевой день внутри непустого ряда, исключение transfer из верхних итогов, отдельный текущий остаток, «—» через `change_percent=null` при нулевом расходе прошлого периода и свежесть только по успешному входящему импорту.
- `backend/tests/test_reports_inventory.py` — проверяет русское название «Приёмка», корректную полную transfer-пару и `integrity_error` для пары с двумя сторонами `stock_transfer_out`.

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend/app/services/reporting_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend/app/services/inventory_movement_report_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend/tests/test_reports_overview.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend/tests/test_reports_inventory.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/night/volna-9-recovery/cards/07-reporting/DEV.md`

## Гейты

- ЗЕЛЁНЫЙ: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend && ruff check app/services/reporting_service.py app/services/inventory_movement_report_service.py tests/test_reports_overview.py tests/test_reports_inventory.py` — `All checks passed!`.
- ЗЕЛЁНЫЙ: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend && mypy app/services/reporting_service.py app/services/inventory_movement_report_service.py app/api/reports.py` — `Success: no issues found in 3 source files`.
- ЗЕЛЁНЫЙ: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend && pytest -q tests/test_reports_overview.py tests/test_reports_inventory.py` — `7 passed in 6.00s`.
- ЗЕЛЁНЫЙ: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting && git diff --check` — замечаний нет.
- `back_guard.py` не применим: атом не добавляет новый роут; ранее созданный `GET /reports/overview` сохранён. В этой рабочей копии `scripts/ci/back_guard.py` отсутствует.
- `check_migrations.py` не применим: миграций в атоме нет.
- БЛОКИРОВКА СРЕДЫ: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting && git add backend/app/services/reporting_service.py backend/app/services/inventory_movement_report_service.py backend/tests/test_reports_overview.py backend/tests/test_reports_inventory.py night/volna-9-recovery/cards/07-reporting/DEV.md && git commit -m "fix(reports): address backend review findings"` — Git не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-1-07-reporting1/index.lock`: `Operation not permitted`. Изменения локально реализованы, но commit SHA отсутствует.

## Не реализовано

- Frontend-находки 1, 3, 5, 7 и 8 из `REVIEW.md` не менялись: они относятся к роли `screen-dev`, а текущая роль ограничена backend.
- Новые эндпоинты и миграции не добавлялись: переделка исправляет существующий read-only контракт и названные ревьюером backend-регрессии.

## Блокеры

- Git-метаданные зарегистрированного worktree находятся вне разрешённой на запись области сессии, поэтому отдельный коммит создать невозможно. Код и `DEV.md` остаются в рабочем дереве; чужие изменения `night/volna-9-recovery/JOURNAL.md` и `night/volna-9-recovery/cards/07-reporting/REVIEW.md` не добавлялись в индекс и не изменялись этой ролью.

## Находки

Нет.

# Фича 7

# DEV · 07-reporting · атом 7 · переделка по review

## Что реализовано

- `GET /reports/inventory` — подтверждена постраничная выдача по товарам и операциям с поиском, разрешёнными сортировками, исключением служебных складов и отдельными сторонами transfer при выборе склада.
- `reporting_service.build_inventory_report` — подтверждены московские календарные границы для offset-less дат, человекопонятные названия операций и `integrity_error` для неполной либо повреждённой transfer-пары без эвристического достраивания.

## Миграции

Нет.

## Тесты

- В `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend/tests/test_reports_inventory.py` добавлен API-сценарий московской границы суток: запись `2026-07-31 22:30 UTC` входит в локальный день 1 августа, а запись ровно `2026-08-01 21:00 UTC` исключается верхней границей.
- Тем же файлом проверены обе группировки, русское название операции «Приёмка», страницы по 50 агрегатов, поиск по названию/артикулу/SKU/ШК, отсутствие служебных складов, отдельная transfer-строка и ошибка целостности для одиночной и повреждённой пары из двух `stock_transfer_out`.

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend/tests/test_reports_inventory.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/night/volna-9-recovery/cards/07-reporting/DEV.md`

## Гейты

- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend && ruff check app/services/reporting_service.py app/api/reports.py tests/test_reports_inventory.py` — `All checks passed!`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend && mypy app/services/reporting_service.py app/api/reports.py` — `Success: no issues found in 2 source files`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend && pytest -q tests/test_reports_inventory.py` — `4 passed in 3.81s`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting && git diff --check` — успешно, ошибок форматирования diff нет.
- `python3 scripts/ci/back_guard.py` — не применим: переделка не добавляет роут; сам скрипт в рабочей копии отсутствует.
- `python3 scripts/ci/check_migrations.py` — не применим: миграций нет; сам скрипт в рабочей копии отсутствует.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting && git add -- backend/tests/test_reports_inventory.py night/volna-9-recovery/cards/07-reporting/DEV.md && git diff --cached --check && git diff --cached --stat && git commit -m "test(reports): cover Moscow inventory boundary"` — не выполнено: Git не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-1-07-reporting1/index.lock`, ошибка `Operation not permitted`.

## Не реализовано

- Находки review по списку складов, декабрьскому пресету, отображению warning и `integrity_error`, а также независимому retry относятся к frontend и не входят в роль `backend-dev` атома 7.
- Находки по заполнению нулевых дней графика и свежести импорта относятся к сводке атома 6; в текущем атоме они не менялись.
- Секреты, ключи, токены, `.env` и кабинеты учётных данных не читались.

## Блокеры

- Изменения локально реализованы и проверены, но не сохранены отдельным коммитом: политика файловой системы не разрешает запись в общий Git-каталог зарегистрированного worktree. Чужое изменение `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/night/volna-9-recovery/JOURNAL.md` не изменялось и не добавлялось в индекс этой ролью.

# Фича 8

# DEV · 07-reporting · атом 8 · переделка по review

## Что реализовано

- `GET /reports/inventory/export.csv` — принимает `sort_by` и `sort_order` и потоково возвращает CSV в той же группировке, фильтрах и порядке, что `GET /reports/inventory`.
- `reporting_service.validated_sort` — единообразно проверяет группировку и разрешённую сортировку таблицы и CSV, не позволяя их контрактам расходиться.
- `reporting_service.build_inventory_csv` — применяет сортировку текущей таблицы для товарной и операционной группировок; русские агрегированные названия операций формируются тем же выражением, что в таблице.

## Миграции

Нет.

## Тесты

- В `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend/tests/test_reports_csv_export.py` добавлено сравнение заголовков, агрегированных строк и порядка CSV с `GET /reports/inventory` при группировке по операциям и сортировке по нетто.
- Там же подтверждено, что операции выгружаются как «Приёмка» и «Отгрузка», а не внутренними кодами.
- Там же добавлен сценарий московских календарных границ: CSV и таблица одинаково включают движение 1 августа в 01:30 МСК и исключают движение ровно на верхней границе 2 августа.
- Повторно проверены существующие сценарии пустого среза, периода свыше 366 дней, совпадения товарных колонок и строк и принудительной seller-области без чужих данных.

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend/app/api/reports.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend/app/services/reporting_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend/tests/test_reports_csv_export.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/night/volna-9-recovery/cards/07-reporting/DEV.md`

## Гейты

- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend && ruff check app/services/reporting_service.py app/api/reports.py tests/test_reports_csv_export.py` — `All checks passed!`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend && mypy app/services/reporting_service.py app/api/reports.py` — `Success: no issues found in 2 source files`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend && pytest -q tests/test_reports_csv_export.py tests/test_reports_inventory.py` — `10 passed in 10.21s`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting && git diff --check` — успешно, ошибок форматирования diff нет.
- `python3 scripts/ci/back_guard.py` — не запускался: переделка не добавляет новый роут, а расширяет параметры существующего `GET /reports/inventory/export.csv`.
- `python3 scripts/ci/check_migrations.py` — не запускался: миграций в атоме нет.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting && git add -- backend/app/api/reports.py backend/app/services/reporting_service.py backend/tests/test_reports_csv_export.py night/volna-9-recovery/cards/07-reporting/DEV.md && git diff --cached --check && git diff --cached --stat && git commit -m "fix(reports): align CSV with table sorting"` — не выполнено: Git не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-1-07-reporting1/index.lock`, ошибка `Operation not permitted`.

## Не реализовано

- Frontend-находки review по списку складов, декабрьскому пресету, отображению предупреждений и `integrity_error`, а также независимому retry не относятся к роли `backend-dev` и файлам атома 8.
- Backend-находки review по дневному графику и свежести WB относятся к overview атома 6; их исправления уже присутствовали в текущем `HEAD` и были только подтверждены чтением кода, без повторного изменения в этом атоме.
- Секреты, ключи, токены, `.env` и кабинеты учётных данных не читались.

## Блокеры

- Изменения локально реализованы и проверены, но отдельный commit создать невозможно: политика файловой системы запрещает запись в общий Git-каталог зарегистрированного worktree. Чужое изменение `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/night/volna-9-recovery/JOURNAL.md` не изменялось и не добавлялось в индекс этой ролью.

# Фича 9

# DEV · 07-reporting · атом 9 · переделка по review

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/App.tsx` — в обеих совместимых точках маршрутизации S-33 в отчёт передаются только операционные склады. Явный `is_operational` имеет приоритет; до интеграции расширенного `/warehouses` служебные склады `FBS WB …` исключаются по тому же правилу, которым миграция заполняет этот флаг.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/apps/seller/SellerApp.tsx` — основной seller-маршрут использует ту же фильтрацию и не открывает селлеру ложную область служебного склада.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/apps/seller/SellerApp.test.tsx` — добавлены точечные unit-кейсы для явного `is_operational=false` и совместимости со старым ответом API без флага.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/tests-e2e/ff-reports.spec.ts` — добавлен `S-33-TC-003/S-33-TC-014`: один физический склад вместе с `FBS WB Архив` не создаёт селектор ложного склада в портале ФФ.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/tests-e2e/seller-reports.spec.ts` — seller-сценарий дополнен проверкой URL, отсутствия чужого селлера и отсутствия селектора при служебном складе с `is_operational=false`.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/night/volna-9-recovery/cards/07-reporting/DEV.md` — отчёт этого ремонтного прохода.

`/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/layouts/AuthedAppLayout.tsx` и `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/screens.registry.json` не менялись: пункт меню, ролевое условие ФФ и регистрация S-33 с двумя маршрутами уже присутствуют; относящихся к ним находок в текущем `REVIEW.md` нет.

## Гейты

- В `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend`: `npm_config_offline=true npx tsc --noEmit -p tsconfig.app.json` — красный до компиляции: локального `tsc` и записи пакета в npm-кэше нет (`ENOTCACHED`).
- В `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting`: `python3 scripts/ui/ui_guard.py` — красный по уже существующим превышениям baseline: `src/App.tsx`, `src/components/WbProductPickerDialog.tsx`, `src/screens/v2/FfFbsSupplyWorkspace.tsx`, `src/screens/v2/SellerInboundDraftScreen.tsx`. Ремонт уменьшил `App.tsx` относительно `HEAD` с 3512 до 3510 строк; baseline не менялась.
- В `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend`: `npm run test:unit -- src/apps/seller/SellerApp.test.tsx` — красный до запуска кейсов: `vitest: command not found`.
- В `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend`: `npm_config_offline=true npx playwright test tests-e2e/ff-reports.spec.ts tests-e2e/seller-reports.spec.ts` — красный до запуска браузера: локального Playwright и записи пакета в npm-кэше нет (`ENOTCACHED`).
- В `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting`: `git diff --check` — зелёный.
- В `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting`: `python3 -m json.tool frontend/screens.registry.json >/dev/null` — зелёный.
- В `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting`: `git add -- frontend/src/App.tsx frontend/src/apps/seller/SellerApp.tsx frontend/src/apps/seller/SellerApp.test.tsx frontend/tests-e2e/ff-reports.spec.ts frontend/tests-e2e/seller-reports.spec.ts night/volna-9-recovery/cards/07-reporting/DEV.md && git diff --cached --check && git diff --cached --stat && git commit -m "fix(reports): hide service warehouse scopes"` — красный на `git add`: Git не может создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-1-07-reporting1/index.lock`, `Operation not permitted`. Чужой `JOURNAL.md` в индекс не добавлялся.

## Не реализовано

- Пункты контракта этого атома и относящаяся к его frontend-маршрутизации находка 1 из `REVIEW.md` реализованы буквально. Автоматическое подтверждение tsc/unit/Playwright отсутствует только из-за отсутствующих frontend-зависимостей и закрытого npm-кэша.
- Находки 2–10 из `REVIEW.md` относятся к `FfReportsPage.tsx`, reporting backend и другим атомам. В рамках роли `screen-dev` и атома 9 эти файлы не менялись.
- Результат локально реализован, но не сохранён отдельным Git-коммитом: sandbox запрещает запись в общий Git-каталог зарегистрированного worktree.

## Находки

- Секреты, ключи, токены, `.env` и кабинеты учётных данных не читались.

# Фича 10

# DEV · 07-reporting · атом 10 · переделка по повторному review

Исправлена гонка частичного отказа сводки: повторный запрос `/reports/overview` теперь использует собственный `AbortController` и не отменяет медленный запрос будущей таблицы, запущенный общей загрузкой фильтра. При смене фильтра старый retry по-прежнему отменяется, поэтому ответ от прежнего среза не может попасть в новый.

Сценарий `S-33-TC-012` усилен: mock таблицы намеренно остаётся незавершённым после первого `503` сводки, оператор нажимает «Повторить», успешный повтор сводки завершается, затем отпускается исходный табличный запрос. Тест требует, чтобы таблица закончила загрузку без второго запроса.

Две остальные находки повторного review уже находились в текущем `HEAD` до этого прохода и подтверждены гейтами: `MovementFlowChart` передаёт несовместимые с MUI свойства через `sx`, а `vitest.config.ts` включает `src/**/*.test.tsx`. Целевой unit-прогон действительно обнаружил четыре `.test.tsx`-файла и выполнил 9 тестов.

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/screens/ff/FfReportsPage.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/tests-e2e/ff-reports.spec.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/night/volna-9-recovery/cards/07-reporting/DEV.md`

`/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/tests-e2e/seller-reports.spec.ts` не менялся: требуемая seller-регрессия уже проверяет отсутствие фильтра селлера, служебного склада и технического предупреждения.

## Гейты

- **ЗЕЛЁНЫЙ:** `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend && npx tsc --noEmit -p tsconfig.app.json`.
- **КРАСНЫЙ вне файлов атома:** `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting && python3 scripts/ui/ui_guard.py`. Храповик сообщил прежние превышения baseline только в `frontend/src/App.tsx`, `frontend/src/components/WbProductPickerDialog.tsx`, `frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx` и `frontend/src/screens/v2/SellerInboundDraftScreen.tsx`; по `FfReportsPage.tsx` показаны улучшения «своя-кнопка 1 → 0» и «своя-таблица 1 → 0». Baseline не менялась.
- **ЗЕЛЁНЫЙ:** `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend && npm run test:unit -- src/apps/seller/SellerApp.test.tsx src/ui-kit/MovementFlowChart.test.tsx src/ui-kit/ReportMetricStrip.test.tsx src/ui-kit/States.test.tsx` — 4 файла, 9 тестов пройдены.
- **ЗЕЛЁНЫЙ:** `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend && npx eslint src/screens/ff/FfReportsPage.tsx tests-e2e/ff-reports.spec.ts tests-e2e/seller-reports.spec.ts src/ui-kit/MovementFlowChart.tsx src/apps/seller/SellerApp.test.tsx src/ui-kit/MovementFlowChart.test.tsx src/ui-kit/ReportMetricStrip.test.tsx src/ui-kit/States.test.tsx vitest.config.ts`.
- **КРАСНЫЙ по ограничению среды до начала browser-кейсов:** `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend && npx playwright test tests-e2e/ff-reports.spec.ts tests-e2e/seller-reports.spec.ts --reporter=line` — API webServer не смог привязаться к `127.0.0.1:18000`, ОС вернула `operation not permitted`; production и живой кабинет Wildberries не затрагивались.
- **ЗЕЛЁНЫЙ, разбор целевых spec:** `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend && npx playwright test tests-e2e/ff-reports.spec.ts tests-e2e/seller-reports.spec.ts --list` — Playwright обнаружил 5 тестов в 2 файлах, включая усиленный retry-кейс и seller-регрессию.
- **ЗЕЛЁНЫЙ:** `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend && git diff --check`.
- **КРАСНЫЙ по ограничению Git-каталога:** `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting && git add -- frontend/src/screens/ff/FfReportsPage.tsx frontend/tests-e2e/ff-reports.spec.ts night/volna-9-recovery/cards/07-reporting/DEV.md && git diff --cached --check && git diff --cached --stat && git commit -m "fix(reports): preserve table during summary retry"` — Git не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-1-07-reporting1/index.lock`: `Operation not permitted`. Чужой `night/volna-9-recovery/JOURNAL.md` не добавлялся.

Полные backend `pytest`, `ruff check .` и `mypy .` не запускались в соответствии с атомарной границей.

## Не реализовано

- Буквально подтвердить усиленный `S-33-TC-012` и seller-регрессию живым Playwright не удалось: локальный API запрещено поднимать системной политикой sandbox. Spec изменён, TypeScript и ESLint зелёные, но это не заменяет browser-прогон.
- `ui_guard.py` нельзя сделать зелёным в границах атома: четыре превышения находятся в чужих файлах и не связаны с текущим diff. Базовая линия не обновлялась.
- Ремонт локально реализован, но не сохранён отдельным Git-коммитом: sandbox разрешает запись в рабочую копию, но запрещает запись в общий Git-каталог зарегистрированного worktree. Проверенного commit SHA для этого прохода нет.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных, production `194.87.96.144` и живой кабинет Wildberries не читались и не затрагивались.

# Фича 11

# DEV · 07-reporting · атом 11 · повторный проход screen-dev

Атом 11 повторно сверен с `CONTRACT.md`, `FEATURES.md`, `MOCKUP.html`, `ARCH-CROSS.md` и актуальным `REVIEW.md`. Все три находки review уже присутствуют исправленными в текущей именованной ветке и были проверены по фактическому коду и тестам: retry сводки не отменяет медленный табличный запрос, MUI-свойства `MovementFlowChart` совместимы с TypeScript, а Vitest обнаруживает `.test.tsx`-спецификации. Дополнительной продуктовой логики и соседних экранов этот проход не менял.

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/night/volna-9-recovery/cards/07-reporting/DEV.md` — записан обязательный артефакт повторного прохода.

Проверенные исправления review уже сохранены в текущей ветке в следующих файлах и не потребовали нового diff в этом проходе:

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/screens/ff/FfReportsPage.tsx` — отдельный `overviewRetryAbortRef` сохраняет выполняющийся табличный запрос при повторе сводки.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/tests-e2e/ff-reports.spec.ts` — сценарий `S-33-TC-012` удерживает таблицу в загрузке до успешного retry и затем проверяет её появление без повторного inventory-запроса; здесь же проверяются обе группировки, вторая страница, неизменность верхней сводки, причина недоступности CSV и MIME `text/csv`.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/tests-e2e/seller-reports.spec.ts` — seller-регрессия общего экрана.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/ui-kit/MovementFlowChart.tsx` — проблемные `alignItems`, `fontWeight` и `flexWrap` передаются через `sx`.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/vitest.config.ts` — маска включает `src/**/*.test.tsx`.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/apps/seller/SellerApp.test.tsx`, `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/ui-kit/MovementFlowChart.test.tsx`, `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/ui-kit/ReportMetricStrip.test.tsx`, `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/ui-kit/States.test.tsx` — ранее пропущенные целевые unit-тесты теперь обнаруживаются и проходят.

## Гейты

- **ЗЕЛЁНЫЙ:** `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend && npx tsc --noEmit -p tsconfig.app.json` — TypeScript завершился с кодом 0 без ошибок.
- **КРАСНЫЙ только вне файлов S-33:** `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting && python3 scripts/ui/ui_guard.py` — прежние превышения храповика находятся в `frontend/src/App.tsx`, `frontend/src/components/WbProductPickerDialog.tsx`, `frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx` и `frontend/src/screens/v2/SellerInboundDraftScreen.tsx`. Для `frontend/src/screens/ff/FfReportsPage.tsx` проверка сообщает улучшения `своя-кнопка 1 → 0` и `своя-таблица 1 → 0`. Baseline не изменялась.
- **ЗЕЛЁНЫЙ, целевые тесты review:** `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend && npx vitest run src/apps/seller/SellerApp.test.tsx src/ui-kit/MovementFlowChart.test.tsx src/ui-kit/ReportMetricStrip.test.tsx src/ui-kit/States.test.tsx` — 4 файла, 9 тестов пройдены.
- **ЗЕЛЁНЫЙ:** `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend && npm run test:unit` — 23 файла, 147 тестов пройдены; все четыре `.test.tsx`-спецификации из review вошли в прогон.
- **КРАСНЫЙ из-за запрета ОС на локальный порт, браузерные кейсы не начались:** `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend && npx playwright test tests-e2e/ff-reports.spec.ts tests-e2e/seller-reports.spec.ts --reporter=line` — webServer не смог привязаться к `127.0.0.1:18000`, ошибка `[Errno 1] operation not permitted`.
- **ЗЕЛЁНЫЙ, обнаружение атомарных Playwright-сценариев:** `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend && npx playwright test tests-e2e/ff-reports.spec.ts tests-e2e/seller-reports.spec.ts --list` — обнаружено 5 тестов в 2 файлах.
- **ЗЕЛЁНЫЙ:** `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend && npx eslint src/screens/ff/FfReportsPage.tsx src/ui-kit/MovementFlowChart.tsx src/apps/seller/SellerApp.test.tsx src/ui-kit/MovementFlowChart.test.tsx src/ui-kit/ReportMetricStrip.test.tsx src/ui-kit/States.test.tsx tests-e2e/ff-reports.spec.ts tests-e2e/seller-reports.spec.ts`.
- **КРАСНЫЙ из-за запрета записи в общий Git-каталог:** `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting && git add -- night/volna-9-recovery/cards/07-reporting/DEV.md && git diff --cached --check && git diff --cached --stat && git commit -m "docs(reports): record atom 11 review verification"` — Git не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-1-07-reporting1/index.lock`, ошибка `Operation not permitted`. Изменённый оркестратором `night/volna-9-recovery/JOURNAL.md` не добавлялся.

Полные backend `pytest`, `ruff check .` и `mypy .` не запускались: атомарная проверка прямо запрещает их на этом шаге.

## Не реализовано

- Кодовые пункты контракта атома 11 и все три находки повторного review присутствуют в ветке буквально; известных отступлений в разрешённом экранном слое нет.
- Живой Playwright-прогон не состоялся из-за системного запрета на привязку локального порта. Поэтому браузерные сценарии не объявляются зелёными, хотя их обнаружение, TypeScript, ESLint и относящиеся unit-тесты прошли.
- Общий `ui_guard.py` остаётся красным из-за четырёх чужих файлов вне разрешённой границы экрана S-33; исправлять их «заодно» и обновлять baseline роль `screen-dev` не имеет права.
- Артефакт локально записан, но отдельный Git-коммит этого прохода создать невозможно из-за запрета sandbox на запись в общий Git-каталог worktree. Проверенного нового commit SHA нет; уже существующие кодовые исправления восстанавливаются из текущего `HEAD` `804eea99a59544477e38ffbf6105dfa871328100`.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных, production `194.87.96.144` и живой кабинет Wildberries не читались и не затрагивались.
