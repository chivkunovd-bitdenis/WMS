# 09-A backend-dev

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/app/models/billing.py` — частичный уникальный индекс профиля ФФ теперь явно ограничен `seller_id IS NULL` и для SQLite.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/alembic/versions/20260822_0094_billing_financial_core.py` — то же условие добавлено в DDL миграции.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/tests/test_billing_models.py` — тест проверяет частичный индекс в SQLite.

## Гейты

- `ruff check .` — FAIL: 83 существующие ошибки вне этого атома; изменённые модель и тест проходят ruff, миграция содержит ранее существовавшие нарушения форматирования.
- `mypy .` — FAIL: 21 существующая ошибка в 6 файлах вне этого атома.
- `pytest` — адресные billing-тесты PASS: `3 passed`; полный прогон не даёт отдельного результата из-за остановки обязательной цепочки на baseline-ruff.
- `python3 scripts/ci/back_guard.py` — BLOCKED: файл отсутствует в этой рабочей копии.
- `python3 scripts/ci/check_migrations.py` — BLOCKED: файл отсутствует в этой рабочей копии.

## Не реализовано

- Находки ревьюера по задачам Celery, API, сервисам, frontend и e2e не относятся к 09-A и намеренно не изменялись.
- Секреты, `.env`, кабинеты учётных данных и боевой прод не читались и не затрагивались.
