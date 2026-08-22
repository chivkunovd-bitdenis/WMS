## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend/app/services/inventory_service.py` — общий writer уже записывает `seller_id=Product.seller_id` и `warehouse_id=StorageLocation.warehouse_id` при создании `InventoryMovement` в той же транзакции, что и изменение остатка.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend/tests/test_inventory_service_reporting_dimensions.py` — сценарий движения с последующей перепривязкой товара и ячейки подтверждает сохранение исходных измерений.

## Гейты

- `ruff check .` — FAIL: 82 существующие ошибки вне файлов атома, включая FBS-сервисы, служебные cleanup-скрипты и несвязанные тесты.
- `mypy .` — FAIL: 21 существующая ошибка в 6 несвязанных файлах; `inventory_service.py` и целевой тест в выводе ошибок отсутствуют.
- `pytest -q tests/test_inventory_service_reporting_dimensions.py` — PASS: 1 passed.
- `python3 scripts/ci/back_guard.py` — BLOCKED: файл отсутствует в рабочей копии.
- `python3 scripts/ci/check_migrations.py` — BLOCKED: файл отсутствует в рабочей копии.

## Не реализовано

- Замечания ревью 1–15 по `reporting_service.py`, API и frontend не относятся к атомарному writer-контракту и намеренно не менялись.
- Новых изменений в коде не потребовалось: требование атома уже выполнено текущей реализацией `record_movement_and_adjust_balance` и покрыто целевым тестом.
- Секреты, ключи, токены и `.env` не читались.
