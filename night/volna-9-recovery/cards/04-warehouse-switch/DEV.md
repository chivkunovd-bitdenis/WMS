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
