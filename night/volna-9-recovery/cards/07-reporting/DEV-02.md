# Backend DEV · 07-reporting · фича 2

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend/app/services/inventory_service.py` — штатная точка записи движения теперь фиксирует `Product.seller_id` и `StorageLocation.warehouse_id` в `InventoryMovement`.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend/tests/test_inventory_service_reporting_dimensions.py` — проверка неизменности измерений после перепривязки товара и ячейки.

## Гейты

- `ruff check .` — НЕ ПРОЙДЕН: 83 ранее существующих ошибки в backend; изменённые файлы проходят отдельную проверку `ruff check app/services/inventory_service.py tests/test_inventory_service_reporting_dimensions.py`.
- `mypy .` — НЕ ПРОЙДЕН: 21 ранее существующая ошибка в 6 файлах; изменённый сервис не добавляет ошибок. Отдельная проверка теста после аннотации проходит по новой проверке типов, кроме существующих ошибок в соседних файлах.
- `pytest tests/test_inventory_service_reporting_dimensions.py` — PASS, 1 тест.
- `pytest` — НЕ ПРОЙДЕН: 812 passed, 5 skipped, 2 failed. Падения в существующем `tests/test_fbs_supply_from_orders.py::test_fbs_cutoff_autoplans_supply_manual_date_and_calendar` и в `tests/test_inventory_movements_report.py::test_inventory_movements_summary_groups_and_period_filter`; второе напрямую создаёт движения без обязательного `warehouse_id` после фичи 1. Новая проверка фичи проходит.
- `python3 scripts/ci/back_guard.py` — НЕ ЗАПУЩЕН: `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/scripts/ci/back_guard.py` отсутствует.
- `python3 scripts/ci/check_migrations.py` — НЕ ЗАПУЩЕН: `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/scripts/ci/check_migrations.py` отсутствует.

## Не реализовано

- Transfer в эту карточку не входит и не изменялся.
- Миграций нет: поля и миграция добавлены фичей 1.

## Находки

- В рабочей копии уже были несвязанные изменения `night/volna-9-recovery/JOURNAL.md`; файл не изменялся.
