# Backend-dev · 03-no-distribution-mode

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/backend/app/services/fbs_packing_box_service.py` — сохранённый признак поставки стал источником истины для readiness и назначения; включение блокируется на строке поставки, повторное включение не меняет аудит.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/backend/app/services/fbs_workspace_service.py` — workspace больше не восстанавливает режим из legacy-ключей коробов.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/backend/app/api/fbs_errors.py` — добавлено понятное сообщение для конфликта назначенных заказов.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/night/volna-9-recovery/cards/03-no-distribution-mode/DEV.md` — этот отчёт.

## Гейты

- ruff: `ruff check .` — FAIL: в репозитории 80 существующих ошибок; изменённые backend-файлы проходят целевую проверку.
- mypy: FAIL на существующих ошибках вне изменённого слоя (`inventory_movement_report_service.py`, `wildberries_credentials_service.py`, `scripts/cleanup_fbs_stub_test_orders.py`, `fbs_stock_sync_service.py`, `fbs_warehouse_binding_service.py`, `wildberries_product_import_service.py`).
- pytest: `backend/tests/test_fbs_packing_box.py` — PASS, 8 passed.
- back_guard.py: NOT RUN: скрипт отсутствует в этой рабочей копии.
- check_migrations.py: NOT RUN: скрипт отсутствует в этой рабочей копии.

## Не реализовано

- Полный backend `mypy` не проходит из-за перечисленных ранее существовавших ошибок, не относящихся к карточке.

## Находки

- Legacy-префиксы в ключах коробов сохраняются для совместимости данных, но больше не влияют на режим поставки.
