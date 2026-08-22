# DEV · 04-warehouse-switch · backend-dev

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/app/services/fbs_supply_validator_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/tests/test_fbs_stock_availability.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/night/volna-9-recovery/cards/04-warehouse-switch/DEV.md`

## Что реализовано

Preflight FBS исключает резервы выбранных заказов при расчёте доступного остатка каждого операционного склада. Поэтому остаток, уже зарезервированный выбранным заказом, не вычитается повторно: достаточный общий остаток не превращается в ложную блокировку.

Добавлен регрессионный тест на доступность выбранного заказа с существующим резервом.

## Миграции

Нет.

## Гейты

- `ruff check backend/app/services/fbs_supply_validator_service.py backend/tests/test_fbs_stock_availability.py` — PASS.
- `ruff check .` из `backend/` — FAIL на существующих несвязанных файлах; затронутые файлы проходят.
- `mypy .` из `backend/` — FAIL на существующих несвязанных файлах; ошибок в изменённых файлах нет.
- Целевой pytest `tests/test_fbs_stock_availability.py -k selected_fbs_order_reservation_can_be_excluded` — PASS (1 passed).
- Полный `pytest` — прерван после 307 passed, 4 skipped и 5 existing failures; падения: `test_fbs_manual_pick.py`, `test_fbs_openapi_contract.py`, `test_fbs_orders_intake.py`, `test_fbs_packaging_fulfillment.py`, `test_fbs_stock_emulator_integration.py`.
- `python3 scripts/ci/back_guard.py` — FAIL: файл отсутствует в данной рабочей копии.
- `python3 scripts/ci/check_migrations.py` — FAIL: файл отсутствует в данной рабочей копии.
- `git diff --check` — PASS.

## Не реализовано

- Остальные находки REVIEW не относятся к этому атомарному backend-слою и не изменялись: измерения `InventoryMovement`, миграция barcode/legacy-складов, API-модели preflight, picking/packing guards, смена склада поставки, frontend и реестр UI-блокировок.

## Находки

- В рабочей копии присутствуют несвязанные изменения в `night/volna-9-recovery/JOURNAL.md`; они не включены в этот результат.
