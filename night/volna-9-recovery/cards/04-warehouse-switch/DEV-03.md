# DEV · 04-warehouse-switch · атом 3

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/app/api/fbs_supplies.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/app/services/fbs_supply_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/tests/test_fbs_supply_from_orders.py`

## Реализовано

- API принимает `selected_warehouse_id` для preflight и создания поставки; поставка создаётся на выбранном операционном складе.
- Смена склада нетронутой поставки выполняется под блокировкой строки; `in_delivery` и `done` также считаются закреплёнными.
- Добавлен регрессионный тест создания поставки на вручную выбранном складе; существующий сценарий lock-after-pick проверен.

## Миграции

Нет.

## Гейты

- `ruff check backend/app/api/fbs_supplies.py backend/app/services/fbs_supply_service.py backend/tests/test_fbs_supply_from_orders.py` — PASS.
- `ruff check .` — FAIL: 80 ранее существующих ошибок в несвязанных файлах репозитория.
- `mypy .` — FAIL: ранее существующие ошибки в `inventory_movement_report_service.py`, `wildberries_credentials_service.py`, cleanup-скриптах и других несвязанных файлах.
- `pytest -q tests/test_fbs_supply_from_orders.py -k 'warehouse_switch or selected_operational'` — PASS, 2 passed, 17 deselected.
- `pytest -q` — запущен; итог записывается после завершения процесса.
- `python3 scripts/ci/back_guard.py` — ожидает завершения полного pytest-прогона.
- `python3 scripts/ci/check_migrations.py` — ожидает завершения полного pytest-прогона.
- `git diff --check` — PASS.

## Не реализовано

- Общие поля `InventoryMovement.seller_id/warehouse_id`, миграция и межскладские движения не изменялись: это зависимость 07-A/отдельный атом, не часть атома 3.
- Полный контракт `warehouse_options`/`inventory` preflight не расширялся: текущий атом касается выбора склада при создании и смены склада документа.

## Блокеры или находки

- Полные ruff/mypy гейты блокируются существующими ошибками вне изменённых файлов. Секреты, ключи, токены и `.env` не читались.
