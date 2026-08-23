# Фича 1

# DEV · 04-warehouse-switch · feature 1

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/ff/FfPackagingPage.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/ff/FfPackagingPage.test.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/night/volna-9-recovery/cards/04-warehouse-switch/DEV.md`

Открытое задание упаковки использует склад самого задания в `WarehouseContextSwitch`, а переключатель заблокирован с причиной `Склад закреплён: открыто задание упаковки`. Сессионный контекст по-прежнему применяется к очереди. Целевой тест покрывает прямую ссылку на задание «Север» при контексте «Юг», проверяет отсутствие вызова `onWarehouseChange` и данные панели «Север»; существующий тест очереди покрывает смену «Север» → «Юг».

## Гейты

- Зелёный: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend && npx tsc --noEmit -p tsconfig.app.json`.
- Зелёный: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend && npm run test:unit -- --run src/screens/ff/FfPackagingPage.test.ts` — `1 passed`, `3 passed`.
- Красный вне границ этого атома: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch && python3 scripts/ui/ui_guard.py`. Новые нарушения только в чужих файлах: `frontend/src/components/WbProductPickerDialog.tsx`, `frontend/src/screens/v2/FfFbsOrdersScreen.tsx`, `frontend/src/screens/v2/FfFbsStockSyncScreen.tsx`, `frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx`, `frontend/src/screens/v2/SellerInboundDraftScreen.tsx`. Для `frontend/src/screens/ff/FfPackagingPage.tsx` guard сообщает улучшение `2146 → 2143`; базовую линию не обновляли.
- Зелёный: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch && git diff --check`.
- Не выполнен из-за sandbox: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch && git add frontend/src/screens/ff/FfPackagingPage.tsx frontend/src/screens/ff/FfPackagingPage.test.ts night/volna-9-recovery/cards/04-warehouse-switch/DEV.md && git diff --cached --check && git commit -m "fix(packaging): lock task warehouse context"` — Git не может создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-1-04-warehouse-switch/index.lock`: `Operation not permitted`.

## Не реализовано

Нет. Реализован только атом 1 из `FEATURES.md`; backend/CI-проверка конкурентной смены склада S-28 намеренно не затрагивалась. Отдельный Git-коммит создать нельзя: sandbox не разрешает запись в общий каталог `.git` зарегистрированного worktree.

## Находки

`ui_guard.py` остаётся красным из-за новых нарушений в файлах других атомов. Секреты, ключи, токены, `.env`, кабинеты учётных данных, боевой production и живой Wildberries не открывались и не изменялись.

# Фича 2

# DEV · 04-warehouse-switch · атом 2

## Что реализовано

- CI: добавлен отдельный job `postgresql-concurrency` с изолированным PostgreSQL 16, переменной `WMS_TEST_DATABASE_URL` и запуском только `pytest -m postgresql_concurrency tests/test_inbound_intake.py`.
- Эндпоинты и сервисы: не изменялись; job исполняет уже принятый `test_submit_serializes_concurrent_warehouse_patch`, который проверяет блокировку, `409 not_draft` и сохранение исходного склада.

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/.github/workflows/ci.yml`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/night/volna-9-recovery/cards/04-warehouse-switch/DEV.md`

## Миграции

Нет.

## Тесты

- Существующий `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/tests/test_inbound_intake.py::test_submit_serializes_concurrent_warehouse_patch` теперь выполняется отдельным PostgreSQL-контуром CI, а не только пропускается в SQLite-контуре.

## Гейты

- Зелёный — `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend && ruff check tests/test_inbound_intake.py` — `All checks passed!`.
- Зелёный — `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend && mypy --follow-imports=skip --disable-error-code import-not-found --disable-error-code untyped-decorator tests/test_inbound_intake.py` — `Success: no issues found in 1 source file`.
- Локальный SQLite-контур ожидаемо пропускает проверку блокировок — `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend && pytest -q -m postgresql_concurrency tests/test_inbound_intake.py` — `1 skipped, 22 deselected`. В новом CI job эта же команда получает PostgreSQL через `WMS_TEST_DATABASE_URL`, поэтому кейс исполняется, а не пропускается.
- Зелёный — `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch && ruby -e 'require "yaml"; YAML.load_file(".github/workflows/ci.yml"); puts "CI YAML parsed"'` — `CI YAML parsed`.
- Зелёный — `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch && git diff --check` — exit 0.
- Отдельный Git-коммит не создан: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch && git add .github/workflows/ci.yml night/volna-9-recovery/cards/04-warehouse-switch/DEV.md && git diff --cached --check && git commit -m "ci(inbound): run warehouse race on postgres"` завершилась ошибкой `Operation not permitted` при создании `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-1-04-warehouse-switch/index.lock`; индекс не изменён.
- `python3 scripts/ci/back_guard.py` не запускался: новый API route не добавляется.
- `python3 scripts/ci/check_migrations.py` не запускался: миграция не добавляется.
- Полные `pytest`, `ruff check .` и `mypy .` не запускались: это запрещено для атомарного шага.

## Не реализовано

Нет: реализован только атом 2 из `FEATURES.md`. Локальный PostgreSQL не запускался, потому что в рабочей среде нет Docker; обязательная изолированная PostgreSQL-проверка перенесена в штатный CI job.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных, живой Wildberries и production `194.87.96.144` не открывались и не изменялись.
