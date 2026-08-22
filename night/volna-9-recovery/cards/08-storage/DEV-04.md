## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/app/api/products.py` — API истории, обмера тары и возврата последней WB-версии.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/app/services/catalog_service.py` — атомарное сохранение объёма тары и чтение истории.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/tests/test_products_api.py` — API-тест сохранения и чтения истории, включая невалидный объём.

## Гейты

- `ruff` — targeted для изменённых backend-файлов: PASS; полный `ruff check .`: FAIL на 80 существующих нарушениях вне этого куска.
- `mypy` — FAIL на 4 существующих ошибках в `wildberries_credentials_service.py`, `fbs_stock_sync_service.py` и `fbs_warehouse_binding_service.py`; изменённые файлы новых ошибок не добавили.
- `pytest` — PASS: `7 passed` для `tests/test_products_api.py tests/test_catalog.py`.
- `back_guard.py` — НЕ ЗАПУЩЕН: файл отсутствует в `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/scripts/ci/`.
- `check_migrations.py` — НЕ ЗАПУЩЕН: файл отсутствует в `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/scripts/ci/`.

## Миграции

Нет: схема уже подготовлена предыдущим куском `20260822_0095_product_dimension_events`.

## Не реализовано

- Полный runtime-тест роли сотрудника с правом `inventory` и запрета другой организации не добавлен в этот проход; tenant-проверка выполняется сервисом, а права — зависимостями API.
- Импорт Wildberries не изменялся: API только возвращает последнюю сохранённую WB-версию.

## Находки

- В рабочем дереве был несвязанный `night/volna-9-recovery/JOURNAL.md`; не изменялся.
