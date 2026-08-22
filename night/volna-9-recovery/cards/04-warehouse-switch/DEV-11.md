# DEV · 04-warehouse-switch · backend-dev

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/app/services/fbs_picking_service.py` — разрешён скан ячейки другого операционного склада; подтверждённый pick создаёт перенос в сортировку склада поставки, повтор ключа идемпотентен, undo использует обратную пару.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/app/services/inventory_service.py` — межскладской transfer сохраняет обе записи `stock_transfer_out`/`stock_transfer_in` с общим `transfer_group_id`.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/app/services/fbs_packaging_integration_service.py` — удалён упаковочный обход в чужую сортировку; без остатка в сортировке упаковка блокируется.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/tests/test_fbs_picking.py` — существующие проверки pick/undo использованы как регрессия атомарного движения.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/tests/test_fbs_packaging_integration.py` — проверки упаковки обновлены под запрет списания из чужой сортировки и без подтверждённого остатка.

## Миграции

Нет. Использованы существующие поля `InventoryMovement.transfer_group_id` и складские модели.

## Тесты

- `backend/tests/test_fbs_picking.py` и `backend/tests/test_fbs_packaging_integration.py` — 23 passed: pick, повтор idempotency key, undo и блокировка упаковочного обхода.

## Гейты

- ruff: PASS для всех изменённых backend-файлов и тестов; полный `ruff check .` — FAIL на 82 существующих ошибках вне этого куска.
- mypy: FAIL на 21 существующей ошибке в 6 несвязанных файлах; новых ошибок в затронутых сервисах по целевой проверке не выявлено.
- pytest: PASS, 23 passed для целевых тестов.
- back_guard.py: НЕ ЗАПУЩЕН — `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/scripts/ci/back_guard.py` отсутствует.
- check_migrations.py: НЕ ЗАПУЩЕН — `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/scripts/ci/check_migrations.py` отсутствует.

## Не реализовано

- Новые API-роуты не добавлялись: изменения встроены в существующие операции pick и упаковки.
- UI и экранный контекст склада не изменялись: это вне роли backend-dev.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных и боевой прод не читались и не изменялись.

## Блокеры

- Полные quality gates ограничены baseline-ошибками и отсутствующими guard-скриптами; целевой backend-срез проверен.
