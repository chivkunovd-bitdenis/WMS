# Backend-dev · 06-picking-list-order

## Изменённые файлы

- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/backend/app/services/fbs_order_tape_print_service.py — разрешён выбор подмножества заказов для существующей строковой печати; порядок и `order_number` вычисляются по полной канонической поставке.
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/backend/tests/test_fbs_supply_assembly.py — тесты одиночной печати с сохранением полного номера и отказа для заказа вне поставки.

## Гейты

- ruff — целевые файлы: PASS (`ruff check app/services/fbs_order_tape_print_service.py tests/test_fbs_supply_assembly.py`); полный запуск репозитория: FAIL на существующих несвязанных нарушениях.
- mypy — FAIL на существующих несвязанных ошибках в `wildberries_credentials_service.py`, `fbs_stock_sync_service.py` и `fbs_warehouse_binding_service.py`; ошибок в изменённых файлах не показано.
- pytest — PASS: `17 passed, 1 skipped` (`tests/test_fbs_supply_assembly.py`).
- back_guard.py — не запущен: файл отсутствует в этой рабочей копии.
- check_migrations.py — не запущен: файл отсутствует в этой рабочей копии.
- git diff --check — PASS.

## Не реализовано

- UI-находки ревью не реализовывались: они относятся к роли screen-dev и не входят в API и данные этого атома.
- Генерация отдельной WMS-этикетки в физическом print-preview не изменялась: текущий backend-атом сохраняет серверные номера и обработку ошибок получения WB-стикеров.
