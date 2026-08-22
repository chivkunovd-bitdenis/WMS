# Backend-dev отчёт · 08-storage

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/app/services/storage_measurement_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/app/models/inventory_movement.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/app/models/warehouse.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/alembic/versions/20260822_0097_storage_movement_scope.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/tests/test_storage_measurement_service.py`

## Гейты

- ruff: целевые файлы — PASS; полный `ruff check .` — FAIL на 80 существующих нарушениях вне этого атома.
- mypy: целевые backend-файлы — PASS.
- pytest: целевые тесты — PASS, 7 passed.
- back_guard.py: не запущен — файл отсутствует в этой рабочей копии.
- check_migrations.py: не запущен — файл отсутствует в этой рабочей копии.

## Не реализовано

- API и фоновый контракт атома не расширялись: исправлен только расчётный слой и его модельная опора.
- Backfill старых движений в `warehouse_id` не выполнялся: это граница внешнего контракта 07-A; новая миграция добавляет поле nullable, не меняя исторические данные предположением.

## Находки

- В рабочей копии отсутствуют `scripts/ci/back_guard.py` и `scripts/ci/check_migrations.py`; это записано как ограничение проверки, не как причина остановки работы.
