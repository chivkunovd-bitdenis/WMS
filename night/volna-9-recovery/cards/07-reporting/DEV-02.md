# Backend Dev · 07-reporting · атом 2

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend/tests/test_inventory_service_reporting_dimensions.py` — усилен регрессионный сценарий: после записи движения товар перепривязывается к другому селлеру, а ячейка — к другому складу; журнал обязан сохранить исходные измерения.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend/app/services/inventory_service.py` — проверен без изменений: штатный writer уже записывает `Product.seller_id` и `StorageLocation.warehouse_id` в одной транзакции с балансом.

## Гейты

- Целевой pytest: PASS (`1 passed`).
- `ruff check .`: FAIL по существующим ошибкам вне изменённых файлов; ошибок в изменённом тесте не обнаружено.
- `mypy .`: FAIL по существующим ошибкам в шести других файлах; изменённые файлы в сообщениях не фигурируют.
- Полный `pytest`: FAIL (`817 passed, 5 skipped, 3 failed`); все три падения в соседних сценариях (`test_fbs_supply_from_orders.py`, `test_fbs_worklist_query_count.py`, `test_inventory_movements_report.py`), целевой тест проходит.
- `python3 scripts/ci/back_guard.py`: BLOCKED — файл отсутствует в этой рабочей копии (`scripts/ci/back_guard.py` не найден).
- `python3 scripts/ci/check_migrations.py`: BLOCKED — файл отсутствует в этой рабочей копии (`scripts/ci/check_migrations.py` не найден).

## Не реализовано

- Новые эндпоинты, сервисы и миграции не требуются для атома 2.
- Замечания ревью к миграции и read-only отчётам относятся к другим атомам/слоям и здесь не изменялись.

## Находки

- В коде и тестах этого атома секреты, ключи, токены и `.env` не читались.
