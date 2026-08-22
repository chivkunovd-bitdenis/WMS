# DEV · 08-storage · атом 5

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/app/models/storage_measurement.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/app/models/storage_statement.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/alembic/versions/20260822_0096_storage_measurements_and_statements.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/tests/test_storage_models.py`

Добавлены переносимые ограничения неотрицательных измерений и корректного диапазона периода. Уникальность `StorageStatement` теперь привязана к `tenant_id + seller_id + warehouse_id + period_start`, поэтому второй документ за тот же календарный месяц создать нельзя.

## Гейты

- `ruff`: PASS для изменённых backend-файлов; полный `ruff check .` — FAIL из-за 93 ранее существовавших ошибок в несвязанных файлах.
- `mypy`: PASS для изменённых моделей; полный `mypy .` — FAIL из-за ошибок в несвязанных сервисах и cleanup-скриптах.
- `pytest`: 5 целевых тестов PASS. Полный запуск остановлен после 32 passed / 63 errors: общие тесты падают на подготовке существующей схемы/фикстур, не в тестах атома.
- `back_guard.py`: не запущен — файл отсутствует по пути `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/scripts/ci/back_guard.py`.
- `check_migrations.py`: не запущен — файл отсутствует по пути `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/scripts/ci/check_migrations.py`.

## Не реализовано

- Проверка соответствия `StorageMeasurement.warehouse_id` фактическому `InventoryMovement.warehouse_id` и исключение служебных складов не добавлены: поля `InventoryMovement.warehouse_id` и `Warehouse.is_operational` принадлежат внешнему фундаменту 07-A и отсутствуют в этой рабочей копии.
- Идемпотентный rebuild, часовой пояс МСК, публикация ledger, API и ролевые ограничения относятся к соседним сервисным/API-атомам и намеренно не изменялись.
