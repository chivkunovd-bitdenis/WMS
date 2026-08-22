## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/app/services/billing_configuration_service.py` — tenant-изолированное сохранение профилей, проверка ИНН, версионное создание тарифов и закрытие предыдущей версии.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/app/api/billing.py` — PUT профиля ФФ, PUT профиля селлера и POST новой ставки с проверкой прав администратора.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/app/main.py` — подключён billing router.

## Гейты

- `ruff` для изменённых файлов: PASS.
- `mypy` для изменённых файлов: BLOCKED существующими ошибками в `inventory_movement_report_service.py`, `wildberries_credentials_service.py`, `fbs_stock_sync_service.py`, `fbs_warehouse_binding_service.py`, `wildberries_product_import_service.py`; ошибок в новых файлах нет.
- `pytest`: полный набор из 816 тестов запущен; на момент отчёта выполняется, ранее затронутый набор `tests/test_staff_packaging_billing.py`: PASS (2 passed).
- `back_guard.py`: BLOCKED, файл `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/scripts/ci/back_guard.py` отсутствует.
- `check_migrations.py`: BLOCKED, файл `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/scripts/ci/check_migrations.py` отсутствует.

## Не реализовано

- GET-методы чтения профилей/тарифов и история ставок не добавлялись: в атомарном пункте 4 явно описано сохранение профилей и создание ставки; чтение относится к экранному/следующему API-контракту.
- Отдельные новые тесты API в этой рабочей копии не добавлялись; существующий backend-набор не содержит готовых фикстур для billing-профилей.

## Находки

- Секреты, ключи, токены, `.env` и кабинеты учётных данных не читались и не затрагивались.
- В рабочем дереве обнаружено несвязанное изменение `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/night/volna-9-recovery/JOURNAL.md`; оно не включалось в реализацию.
