# Backend DEV · 07-reporting · фича 1

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend/app/models/inventory_movement.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend/alembic/versions/20260822_0094_inventory_movement_reporting_dimensions.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend/tests/test_inventory_movement_reporting_dimensions.py`

Модель и миграция добавляют `seller_id`, обязательный `warehouse_id` и флаг
`reporting_dimensions_legacy`; backfill использует связи товара и ячейки, а также
создаёт индексы tenant/seller/warehouse по времени.

## Гейты

- `ruff check app/models/inventory_movement.py tests/test_inventory_movement_reporting_dimensions.py` — PASS.
- `mypy app/models/inventory_movement.py` — PASS.
- `pytest tests/test_inventory_movement_reporting_dimensions.py` — PASS, 2 теста.
- `pytest` — НЕ ПРОЙДЕН: полный набор остановлен на существующих writer-тестах, которые создают `InventoryMovement` без `warehouse_id`; заполнение новых движений относится к фиче 2.
- `python3 scripts/ci/back_guard.py` — НЕ ЗАПУЩЕН: файл отсутствует в рабочей копии.
- `python3 scripts/ci/check_migrations.py` — НЕ ЗАПУЩЕН: файл отсутствует в рабочей копии.

## Не реализовано

- Заполнение `seller_id` и `warehouse_id` в штатном сервисе записи движений не менялось: это отдельная фича 2 по контракту.
- Роуты и read-only API отчёта не менялись: они относятся к последующим фичам.
- Полный pytest требует завершения фичи 2, потому что текущие writer-пути ещё не передают новые обязательные измерения.
