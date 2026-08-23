# 09-billing · backend-dev · атом 3

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/alembic/versions/20260822_09a_billing_financial_core.py` — добавлено обязательное поле `event_kind`; уникальный ключ факта теперь содержит tenant, услугу, исходный документ и вид события.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/app/models/billing.py` — модель журнала синхронизирована со схемой: `event_kind` и тот же уникальный ключ.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/app/services/billing_ledger_service.py` — активное начисление определяется как запись без сторно; после сторно повторный факт получает детерминированный новый `event_kind`, а одинаковый активный факт по-прежнему возвращает существующую запись.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/tests/test_billing_ledger_service.py` — добавлены сценарии «начисление → сторно → повторное начисление» и повторного вызова без сторно.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/night/volna-9-recovery/cards/09-billing/DEV.md` — этот отчёт.

## Гейты

- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend && pytest -q tests/test_billing_ledger_service.py` — `7 passed`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend && ruff check app/services/billing_ledger_service.py app/models/billing.py alembic/versions/20260822_09a_billing_financial_core.py tests/test_billing_ledger_service.py` — `All checks passed!`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend && mypy app/services/billing_ledger_service.py app/models/billing.py` — `Success: no issues found in 2 source files`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend && pytest -q tests/test_billing_ledger_service.py tests/test_billing_financial_core_migration.py` — `10 passed, 2 warnings`; предупреждения Alembic о `path_separator` не относятся к атому.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing && python3 scripts/ci/back_guard.py && python3 scripts/ci/check_migrations.py` — не запущены: оба файла отсутствуют в этой рабочей копии. Поиск через `rg --files` подтвердил отсутствие `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/scripts/ci/back_guard.py` и `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/scripts/ci/check_migrations.py`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing && git add … && git commit -m 'fix(billing): allow charge after reversal'` — не выполнен: Git не получил разрешение создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-3-09-billing1/index.lock`. Изменения остаются в рабочем дереве без commit SHA.

## Не реализовано

- Следующие атомы карточки `09-billing` не затрагивались. Из находок `REVIEW.md` исправлена только №4, относящаяся к текущему слою и атому.
- Внешние API, секреты, токены, `.env`, кабинеты учётных данных и боевой прод не открывались и не изменялись.
