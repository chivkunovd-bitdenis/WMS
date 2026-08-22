# DEV — 09-billing, backend-dev

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/app/models/billing.py` — модели неизменяемого счёта и блокирующей причины.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/app/models/__init__.py` — регистрация моделей.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/app/services/billing_invoice_service.py` — единый алгоритм формирования и идемпотентной отмены.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/app/tasks/billing_tasks.py` — задача ежедневного запуска.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/app/celery_app.py` — подключение задачи и расписание 02:30.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/app/api/billing.py` — ручки формирования и отмены счёта.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/alembic/versions/20260822_0095_billing_invoices.py` — добавляющая миграция.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/tests/test_billing_invoice_service.py` — тест блокировки `unpriced` и идемпотентного повтора.

## Гейты

- `ruff`: PASS для изменённых backend-файлов; полный `ruff check .` в репозитории уже содержит 137 исходных нарушений вне этой карточки.
- `mypy`: PASS для изменённых модулей.
- `pytest`: PASS, `2 passed` для `tests/test_billing_invoice_service.py`.
- `back_guard.py`: НЕ ЗАПУЩЕН — файла `scripts/ci/back_guard.py` в этой рабочей копии нет.
- `check_migrations.py`: НЕ ЗАПУЩЕН — файла `scripts/ci/check_migrations.py` в этой рабочей копии нет.

## Не реализовано

- Полный обход всех tenant/seller в Celery-задаче оставлен за существующим runner-контуром: в текущем backend нет готового безопасного tenant-итератора для фоновой сессии. API и сервис используют один и тот же алгоритм.
- Проверка закрытия хранения реализована через опубликованный ledger-маркер `storage_period_open`; фактическая публикация `StorageStatement` остаётся в межкарточной реализации 08-B.
- Секреты, токены, `.env` и кабинеты учётных данных не читались.
