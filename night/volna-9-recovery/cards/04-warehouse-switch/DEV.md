# DEV · 04-warehouse-switch · атом 3

## Изменённые файлы

- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/app/api/fbs_supplies.py
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/app/services/fbs_supply_reconcile_service.py
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/app/services/fbs_supply_service.py
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/app/services/fbs_supply_validator_service.py
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/night/volna-9-recovery/cards/04-warehouse-switch/DEV.md

## Что реализовано

- Preflight API теперь сохраняет в ответе `stock_preflight`, варианты операционных складов, рекомендованный склад и агрегированный inventory.
- Выбранный операционный склад участвует в расчёте текущего остатка и рекомендаций; источник межскладского подбора выбирается по максимальному доступному остатку.
- Idempotency-хэш создания поставки учитывает `selected_warehouse_id`, поэтому повтор с тем же ключом и другим складом не переиспользует старый результат.

## Миграции

Нет.

## Тесты

- `backend/tests/test_fbs_supply_from_orders.py`: targeted набор проверяет preflight и создание/смену склада; 17 passed, 1 skipped, 1 календарный fail на фиксированной дате `2026-08-15`, уже прошедшей в текущем окружении.

## Гейты

- ruff: PASS для изменённых backend-файлов.
- mypy: FAIL из-за 4 предсуществующих ошибок в `wildberries_credentials_service.py`, `fbs_stock_sync_service.py`, `fbs_warehouse_binding_service.py`.
- pytest: 17 passed, 1 skipped, 1 unrelated calendar failure.
- back_guard.py: запуск невозможен — `scripts/ci/back_guard.py` отсутствует в этой рабочей копии.
- check_migrations.py: запуск невозможен — `scripts/ci/check_migrations.py` отсутствует в этой рабочей копии.

## Не реализовано

- UI-находки REVIEW и соседние picking/packing/transfer-задачи не входят в backend-атом 3.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных и боевой прод не открывались и не изменялись.

## Блокеры

- Только общие инфраструктурные гейты: отсутствующие guard-скрипты, предсуществующие mypy-ошибки и календарный тест с устаревшей фиксированной датой.
