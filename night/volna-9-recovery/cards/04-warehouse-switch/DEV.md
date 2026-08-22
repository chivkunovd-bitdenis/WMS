# Backend development report · 04-warehouse-switch

## Изменённые файлы

- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/app/models/warehouse.py
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/app/services/catalog_service.py
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/app/api/warehouses.py
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/alembic/versions/20260822_0094_warehouse_operational_barcode.py
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/tests/test_warehouses.py

## Гейты

- ruff: PASS for changed backend files; full `ruff check .` is blocked by pre-existing errors in unrelated files.
- mypy: changed files type-check apart from existing repository errors in unrelated services; full gate reports 4 pre-existing errors.
- pytest: PASS — `tests/test_warehouses.py tests/test_catalog.py`, 7 passed.
- back_guard.py: NOT RUN — script is absent from this checkout.
- check_migrations.py: NOT RUN — script is absent from this checkout.

## Не реализовано

- Остальные фичи карточки 04 не реализованы: выполнен только атомарный кусок 1.
- Full-repository gates remain red because of unrelated baseline errors; no unrelated fixes were made.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных и боевой прод не читались и не изменялись.
