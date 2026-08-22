# DEV · 04-warehouse-switch · backend-dev

## Изменённые файлы

- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/app/services/fbs_picking_service.py
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/app/services/inventory_service.py
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/app/models/inventory_movement.py
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/alembic/versions/20260822_0095_inventory_movement_dimensions.py
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/tests/test_fbs_picking.py
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/night/volna-9-recovery/cards/04-warehouse-switch/DEV.md

## Что реализовано

- `scan_pick_product` повторно проверяет ключ идемпотентности после блокировки поставки; кросс-складской FBS-pick и его undo явно разрешают только свой специализированный путь переноса.
- `transfer_on_hand_between_locations` снова запрещает перемещение между разными складами по умолчанию; товар без `seller_id` можно принять и записать в журнал, без постановки задачи публикации WB.

## Миграции

- `20260822_0095_inventory_movement_dimensions`: `seller_id` в движениях остаётся nullable, чтобы не ломать исторические и обычные FF-товары без селлера; `warehouse_id` остаётся обязательным.

## Тесты

- `test_generic_inventory_transfer_rejects_another_warehouse`: общий writer отклоняет межскладской перенос.
- `test_fbs_picking.py`: 9 passed, включая идемпотентность и undo полной пары.
- `test_fbs_packaging_integration.py`: 15 passed, включая запрет списания из чужой сортировки и отсутствие обхода.

## Гейты

- ruff: целевые изменённые файлы — `All checks passed`; полный `ruff check .` не прошёл из-за 80 существующих ошибок вне этого атома.
- mypy: не прошёл из-за 4 существующих ошибок в `wildberries_credentials_service.py`, `fbs_stock_sync_service.py` и `fbs_warehouse_binding_service.py`; изменённые файлы не перечислены среди ошибок.
- pytest: целевые `test_fbs_picking.py` и `test_fbs_packaging_integration.py` — 24 passed (прогнаны отдельными группами).
- back_guard.py: не запущен — файла `scripts/ci/back_guard.py` в этой рабочей копии нет.
- check_migrations.py: не запущен — файла `scripts/ci/check_migrations.py` в этой рабочей копии нет.
- git diff --check: пройден.

## Не реализовано

- Не добавлялись API и UI-пункты из соседних атомов. Файл `fbs_packaging_integration_service.py` не менялся: запрет списания из чужой сортировки уже реализован и покрыт тестом.

## Блокеры

Нет. Секреты, токены, `.env` и кабинеты учётных данных не читались.
