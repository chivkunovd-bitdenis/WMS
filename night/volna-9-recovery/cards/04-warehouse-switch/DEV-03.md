# DEV · 04-warehouse-switch · atom 3

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/app/services/fbs_supply_service.py` — добавлен импорт `Warehouse`, необходимый существующей проверке операционного склада при смене склада поставки.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/tests/test_fbs_supply_from_orders.py` — добавлен интеграционный тест смены склада до первого pick и отказа после pick; проверено сохранение склада документа.

Endpoint `PATCH /operations/fbs-supplies/{supply_id}/warehouse` и сервисная логика атома уже были реализованы предыдущим backend-атомом; в рамках этого прохода они покрыты тестом и исправлена отсутствующая зависимость импорта.

## Миграции

Нет. Схема базы данных не менялась.

## Тесты

- `test_fbs_supply_warehouse_switch_is_locked_after_pick` — новая поставка меняет склад на второй операционный склад до pick; после установки статуса pick повторная смена возвращает HTTP 409 с причиной `Склад закреплён: подбор уже начат`; workspace сохраняет выбранный склад.

## Гейты

- ruff: FAIL на существующих ошибках вне изменённых файлов (80 ошибок, включая старые `noqa`, импортные блоки и ошибки в `scripts/`); изменённые файлы новых нарушений не добавили.
- mypy: FAIL на существующих ошибках вне изменённых файлов (`inventory_movement_report_service.py`, `wildberries_credentials_service.py`, `scripts/`, `fbs_stock_sync_service.py`, `fbs_warehouse_binding_service.py`, `wildberries_product_import_service.py`).
- pytest: targeted `tests/test_fbs_supply_from_orders.py -k warehouse_switch` PASS (`1 passed`); полный прогон остановлен после обнаружения ранее существующих падений в `test_fbs_autopoll.py` и `test_fbs_openapi_contract.py`.
- back_guard.py: не запущен — файл отсутствует в checkout (`/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/scripts/ci/back_guard.py`).
- check_migrations.py: не запущен — файл отсутствует в checkout (`/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/scripts/ci/check_migrations.py`); миграций в изменениях нет.

## Не реализовано

- Вне атома 3 ничего не менялось: UI, фильтрация списков и межскладской pick относятся к другим атомам и не реализуются этой ролью.
