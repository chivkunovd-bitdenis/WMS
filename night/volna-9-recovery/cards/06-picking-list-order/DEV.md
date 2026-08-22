# Backend development · 06-picking-list-order · атомарный кусок 4

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/backend/app/services/fbs_order_tape_print_service.py` — полная поставка проверяется целиком; заказы сортируются сервером тем же каноном, что лист подбора; каждому заказу и ошибке получения стикера возвращается постоянный `order_number`.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/backend/app/api/fbs_supplies.py` — опубликованы `order_number` в ленте и ошибках.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/backend/tests/test_fbs_supply_assembly.py` — добавлена проверка независимости канонического порядка от порядка входного состава.

## Гейты

- `ruff`: PASS для изменённых backend-файлов.
- `mypy`: BLOCKED существующими ошибками в `wildberries_credentials_service.py`, `fbs_stock_sync_service.py`, `fbs_warehouse_binding_service.py`; в изменённых файлах новых ошибок не выявлено.
- `pytest`: PASS целевых тестов: `2 passed, 13 deselected` для канона/лист-подбора; смежный tape/sticker smoke: `1 passed, 19 deselected`.
- `back_guard.py`: BLOCKED — `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/scripts/ci/back_guard.py` отсутствует.
- `check_migrations.py`: BLOCKED — `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/scripts/ci/check_migrations.py` отсутствует; миграций нет.

## Не реализовано

- Новая бинарная генерация WMS-этикетки с номером не добавлялась: существующий контракт печати уже возвращает служебные артефакты, а этот атомарный кусок закрепляет серверный состав, порядок и номер заказа.
- UI и клиентская типизация не изменялись по границе backend-dev.

## Находки

- Секреты, ключи, токены и `.env` не читались.
- Боевой прод и живой кабинет Wildberries не затрагивались.
