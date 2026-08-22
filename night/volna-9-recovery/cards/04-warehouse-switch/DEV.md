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
