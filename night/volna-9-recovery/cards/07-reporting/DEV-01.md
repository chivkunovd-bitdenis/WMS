# Backend-dev · 07-reporting · атом 1

## Изменённые файлы

- Изменений в backend-файлах по результатам re-review не потребовалось: замечания REVIEW.md относятся к 07-B reporting API/UI, а не к 07-A модели и миграции.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend/app/models/inventory_movement.py` — проверен контракт `seller_id`, обязательный `warehouse_id` и `reporting_dimensions_legacy`.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend/alembic/versions/20260822_0094_inventory_movement_reporting_dimensions.py` — проверен backfill коррелированными подзапросами, отказ при неразрешимом `warehouse_id`, внешние ключи и составные индексы.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend/tests/test_inventory_movement_reporting_dimensions.py` — проверены модель и текстовые инварианты миграции.

## Гейты

- `ruff check .` — FAIL: 82 уже существующих ошибок в несвязанных backend-файлах; ошибок в перечисленных файлах атома в выводе нет.
- `mypy .` — FAIL: 21 уже существующая ошибка в 6 несвязанных файлах; ошибок в перечисленных файлах атома нет.
- `pytest -q tests/test_inventory_movement_reporting_dimensions.py` — PASS, 2 passed.
- `pytest` — не запускался целиком после целевого теста: полный backend уже блокируется перечисленными ruff/mypy-ошибками.
- `python3 scripts/ci/back_guard.py` — не запущен: файла `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/scripts/ci/back_guard.py` в этой рабочей копии нет.
- `python3 scripts/ci/check_migrations.py` — не запущен: файла `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/scripts/ci/check_migrations.py` в этой рабочей копии нет.

## Не реализовано

- Находки 1–15 из REVIEW.md, относящиеся к `reporting_service.py`, frontend, UI-реестру, E2E и `docs/blockers`, не реализовывались: они находятся вне атома 07-A и вне роли backend-dev для указанных трёх файлов.
- Полное применение миграции к живой базе не выполнялось: для этого в рабочей копии нет предусмотренного migration guard/тестового окружения; секреты, `.env`, ключи и кабинеты учётных данных не читались.

## Находки

- В текущей рабочей копии обязательные guard-скрипты отсутствуют по указанным путям.
