# Backend development · 06-picking-list-order

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/backend/app/services/fbs_supply_service.py` — серверная канонизация товарных групп, порядок заказов и вычисление диапазонов.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/backend/app/api/fbs_supplies.py` — поля `number_start`, `number_end`, `order_ids` в ответе существующего API листа.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/backend/tests/test_fbs_supply_assembly.py` — проверки диапазонов, полного состава и повторяемости ответа.

## Гейты

- `ruff`: PASS для изменённых backend-файлов; полный `ruff check .` BLOCKED существующими ошибками в несвязанных файлах.
- `mypy`: BLOCKED существующими 4 ошибками в `wildberries_credentials_service.py`, `fbs_stock_sync_service.py`, `fbs_warehouse_binding_service.py`; изменённые файлы не добавили ошибок.
- `pytest`: целевой `-k picking_list`: PASS, 1 passed; полный набор запущен и прерван после 29% без ошибки в выполненных тестах.
- `back_guard.py`: BLOCKED — файл `scripts/ci/back_guard.py` отсутствует в этой рабочей копии.
- `check_migrations.py`: BLOCKED — файл `scripts/ci/check_migrations.py` отсутствует в этой рабочей копии; миграций нет.

## Не реализовано

- Ничего из API и данных этой атомарной карточки не оставлено без реализации.
- UI листа и серверная лента относятся к другим атомарным кускам и не изменялись.

## Блокеры

- Commit не создан: Git не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-3-06-picking-list-order/index.lock` из-за ограничения прав общей мета-папки worktree. Изменения остаются в рабочем diff до восстановления права на запись владельцем окружения.
