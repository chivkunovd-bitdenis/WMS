# Backend Dev · 07-reporting

## Изменённые файлы

- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend/app/api/reports.py — добавлен seller_id для FF-фильтра в inventory и CSV; seller-портал сохраняет принудительный scope.
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend/app/services/reporting_service.py — исторический seller join по InventoryMovement, корректная проверка transfer-пар вне warehouse-фильтра, согласованные поля строк и CSV, исключение служебных складов из overview.
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/night/volna-9-recovery/cards/07-reporting/DEV.md — этот отчёт.

## Гейты

- ruff: `ruff check app/services/reporting_service.py app/api/reports.py tests/test_reports_inventory.py` — PASS.
- mypy: `mypy app/services/reporting_service.py app/api/reports.py` — PASS.
- pytest: `pytest tests/test_reports_inventory.py` — PASS (команда завершилась без вывода тест-раннера).
- back_guard.py: не найден в этой рабочей копии; запуск из корня невозможен.
- check_migrations.py: не найден в этой рабочей копии; запуск из корня невозможен.

## Не реализовано

- Новая миграция не добавлялась: миграция `20260822_0094_inventory_movement_reporting_dimensions.py` уже содержит исправленный PostgreSQL-safe backfill из предыдущего прохода.
- Персональный `current_balance` в каждой строке товарной таблицы не добавлялся: текущий контракт этого атома отдаёт агрегаты движения и поля таблицы, а баланс остаётся в overview.

## Находки

- В рабочей копии отсутствуют `scripts/ci/back_guard.py` и `scripts/ci/check_migrations.py`; это инфраструктурное ограничение checkout, не изменение кода.
