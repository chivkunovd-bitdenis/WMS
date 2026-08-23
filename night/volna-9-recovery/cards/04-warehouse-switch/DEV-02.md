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
