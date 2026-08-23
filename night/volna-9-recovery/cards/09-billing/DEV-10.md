# 09-billing — атом 10: ежедневное автоматическое формирование счетов

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/tests/test_billing_tasks.py` — добавлен сценарий `S-31-TC-006`, который запускает `_run_billing_invoices_daily` на реальной изолированной тестовой БД с двумя селлерами и двумя закрытыми месяцами, проверяет сформированные счета, commit каждой пары «селлер × месяц» и повтор без дублей.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/night/volna-9-recovery/cards/09-billing/DEV.md` — отчёт по атому 10.

## Миграции

Нет: атом добавляет только поведенческую регрессионную проверку ежедневной задачи.

## Гейты

- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend && ruff check tests/test_billing_tasks.py tests/test_billing_invoice_service.py` — `All checks passed!`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend && mypy app/tasks/billing_tasks.py app/services/billing_invoice_service.py` — `Success: no issues found in 2 source files`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend && pytest -q tests/test_billing_tasks.py tests/test_billing_invoice_service.py` — `12 passed`.
- `back_guard.py` и `check_migrations.py` не применимы: атом не добавляет маршрут или миграцию.

## Не реализовано

Нет: реализована ровно находка 15 ревью и проверка из атома 10. Сервис формирования счёта не менялся, потому что тест подтверждает его существующую идемпотентность при запуске через ежедневную задачу.

## Блокеры

- Изолированная среда запрещает запись в git-метаданные общего checkout: `git add backend/tests/test_billing_tasks.py night/volna-9-recovery/cards/09-billing/DEV.md` не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-3-09-billing1/index.lock` (`Operation not permitted`). Поэтому изменения реализованы и проверены локально, но не сохранены отдельным Git-коммитом; SHA отсутствует.
