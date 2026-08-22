# DEV · 06-picking-list-order · атом 3

## Изменённые файлы

В рамках переделки по REVIEW.md backend-файлы атома не изменялись: серверная реализация уже присутствует в рабочей копии и соответствует контракту.

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/backend/app/services/fbs_supply_service.py` — `get_picking_list` строит группы по `(article, sku_code, size, product_name)`, сортирует группы и заказы детерминированно, считает непрерывные номера и полный `order_ids`.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/backend/app/api/fbs_supplies.py` — endpoint `GET /operations/fbs-supplies/{supply_id}/picking-list` отдаёт `number_start`, `number_end` и `order_ids`.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/backend/tests/test_fbs_supply_assembly.py` — интеграционный сценарий проверяет несколько товарных групп, диапазоны, канонический состав и повторный идентичный запрос.

Находки REVIEW.md 1–6 относятся к frontend и печати следующего атома; находка 7 требует проверки `order-print-tape` из атома 4, поэтому в этот backend-атом не включалась.

## Гейты

- `ruff check .` — FAIL: 82 существующие ошибки в несвязанных файлах backend (в том числе `app/api/fbs_sellers.py`, `app/services/fbs_stock_sync_service.py`, scripts и других тестах); файлы атома не указаны в выводе.
- `mypy .` — FAIL: 21 существующая ошибка в 6 несвязанных файлах (`inventory_movement_report_service.py`, `wildberries_credentials_service.py`, cleanup-скрипты, `fbs_stock_sync_service.py`, `fbs_warehouse_binding_service.py`, `wildberries_product_import_service.py`).
- `pytest tests/test_fbs_supply_assembly.py` — PASS: `17 passed, 1 skipped`.
- `python3 scripts/ci/back_guard.py` — NOT RUN: `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/scripts/ci/back_guard.py` отсутствует.
- `python3 scripts/ci/check_migrations.py` — NOT RUN: `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/scripts/ci/check_migrations.py` отсутствует.

## Не реализовано

- Исправления frontend-печати, предпросмотра, состояний `shortage/order_errors` и browser/e2e-проверки не реализованы: они находятся за пределами backend-атома 3.
- Новых миграций нет.
- Новых backend-изменений не потребовалось: REVIEW.md подтверждает, что серверный порядок, диапазоны, tenant-фильтр и повторяемость уже работают.
