# DEV · 08-storage · атом 7

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/app/services/storage_statement_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/app/api/storage.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/night/volna-9-recovery/cards/08-storage/DEV.md`

## Гейты

- `ruff`: PASS для изменённых backend-файлов.
- `mypy`: FAIL в существующих несвязанных местах `wildberries_credentials_service.py`, `fbs_stock_sync_service.py`, `fbs_warehouse_binding_service.py`.
- `pytest`: PASS: `tests/test_storage_statement_service.py` — 1 passed.
- `back_guard.py`: НЕ ЗАПУЩЕН — файл отсутствует в этой рабочей копии (`scripts/ci/back_guard.py`).
- `check_migrations.py`: НЕ ЗАПУЩЕН — файл отсутствует в этой рабочей копии (`scripts/ci/check_migrations.py`).

## Не реализовано

- Общие модели `BillingTariffVersion` / `BillingLedgerEntry` отсутствуют в текущей рабочей копии; собственный storage-ledger не добавлялся по обязательной границе `ARCH-CROSS.md`.
- Создание нулевого statement и полноценная A4-схема с SKU, ставкой-снимком и итогом требуют соседнего слоя измерений/09-A; в этом атоме не добавлялись новые таблицы и миграции.
- Полный набор конкурентных интеграционных тестов не добавлен: доступные в копии тесты не содержат billing-моделей для исполнения фиксации.

Блокеры: нет; ограничения отражены выше.
