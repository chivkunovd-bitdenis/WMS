# 09-billing — атом 8: даты строк счёта по МСК

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/app/services/billing_invoice_service.py` — дата исходного документа в детализации счёта определяется после перевода времени факта в `Europe/Moscow`.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/tests/test_billing_invoice_service.py` — добавлен сервисный сценарий границы московской полуночи: `2025-06-30T21:30:00Z` относится к `2025-07-01` и к периоду июля.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/night/volna-9-recovery/cards/09-billing/DEV.md` — отчёт по атому.

## Гейты

- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend && ruff check app/services/billing_invoice_service.py tests/test_billing_invoice_service.py` — `All checks passed!`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend && mypy app/services/billing_invoice_service.py` — `Success: no issues found in 1 source file`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend && pytest -q tests/test_billing_invoice_service.py` — `10 passed in 0.15s`.
- `back_guard.py` и `check_migrations.py` не применимы: атом не добавляет маршрут или миграцию.

## Не реализовано

- Нет: атом 8 ограничен серверной датой строки счёта и её сервисной проверкой. Форматирование дат на экране относится к отдельному атому 14.

## Блокеры

- Git-коммит не создан: `git add backend/app/services/billing_invoice_service.py backend/tests/test_billing_invoice_service.py night/volna-9-recovery/cards/09-billing/DEV.md` не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-3-09-billing1/index.lock` (`Operation not permitted`). Реализация и артефакт находятся в этой рабочей копии, но без commit SHA результат нельзя считать сохранённым в Git.
