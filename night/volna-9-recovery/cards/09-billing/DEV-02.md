## Изменённые файлы

- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/alembic/versions/20260822_09a_billing_financial_core.py
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/app/models/billing.py
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/tests/test_billing_financial_core_migration.py
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/night/volna-9-recovery/cards/09-billing/DEV.md

## Гейты

- Зелёный: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend && ruff check app/models/billing.py alembic/versions/20260822_09a_billing_financial_core.py tests/test_billing_financial_core_migration.py` — ошибок нет.
- Зелёный: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend && mypy app/models/billing.py` — `Success: no issues found in 1 source file`.
- Зелёный: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend && pytest -q tests/test_billing_financial_core_migration.py` — `3 passed`; Alembic вывел 2 унаследованных предупреждения `path_separator`.
- Зелёный: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing && git diff --check` — ошибок пробелов нет.
- `back_guard.py` не применим: в атоме нет нового маршрута. `check_migrations.py` не запущен: атом исправляет существующую миграцию, новый файл миграции не добавляет; скрипт также отсутствует в этой рабочей копии.
- Не сохранено новым Git-коммитом: `git add backend/alembic/versions/20260822_09a_billing_financial_core.py backend/app/models/billing.py backend/tests/test_billing_financial_core_migration.py night/volna-9-recovery/cards/09-billing/DEV.md && git commit -m "fix(09-billing): store financial core in kopecks"` не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-3-09-billing1/index.lock` (`Operation not permitted`).

## Не реализовано

Нет. В пределах атома `BillingTariffVersion.amount` и `BillingLedgerEntry.rate/amount` переведены из дробных рублей в целые копейки как в Alembic-схеме, так и в ORM. Миграционный и модельный тесты фиксируют тип `INTEGER`; тест преобразования подтверждает, что 4550 копеек отображаются как 45,50 ₽.

## Находки

Секреты, ключи, токены, `.env` и кабинеты учётных данных не читались и не изменялись.
