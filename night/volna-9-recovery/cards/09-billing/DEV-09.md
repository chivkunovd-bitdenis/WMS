# 09-billing — атом 9: API журнала для сторно

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/app/api/billing.py` — `GET /billing/ledger` возвращает явный `entry_type`; для строки сторно отдаёт `source_type` и `source_id` исходной складской операции, а не технический `billing_reversal`.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/tests/test_billing_invoice_api.py` — добавлен API-сценарий `S-31-TC-016` с исходным начислением и сторно: проверяет тип строки, ссылку на исходный документ и его номер.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/night/volna-9-recovery/cards/09-billing/DEV.md` — отчёт по атому.

## Гейты

- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend && ruff check app/api/billing.py tests/test_billing_invoice_api.py` — `All checks passed!`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend && mypy app/api/billing.py` — не пройдено из-за двух существующих ошибок в не изменявшемся `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/app/services/billing_configuration_service.py:200,203`: присваивание `Decimal` полю, выведенному как `int | None`. В `billing.py` и добавленном API-сценарии mypy-ошибок не сообщил.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend && pytest -q tests/test_billing_invoice_api.py` — `5 passed in 4.11s`.
- `back_guard.py` и `check_migrations.py` не применимы: атом не добавляет маршрут или миграцию.

## Не реализовано

- Нет: атом ограничен форматом ответа существующего `GET /billing/ledger` и его API-проверкой. Экранное представление сторно выполняется отдельным фронтенд-атомом 13.

## Блокеры

- Mypy-ошибки в `billing_configuration_service.py` зафиксированы в секции гейтов как унаследованные и не относятся к файлам или слою атома 9.
- Отдельный commit не создан: `git add backend/app/api/billing.py backend/tests/test_billing_invoice_api.py night/volna-9-recovery/cards/09-billing/DEV.md` не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-3-09-billing1/index.lock` (`Operation not permitted`). Реализация находится в рабочей копии, но без commit SHA её нельзя считать сохранённой в Git.
