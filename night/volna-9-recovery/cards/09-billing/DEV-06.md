# 09-billing — backend-dev, атом 6

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/app/services/billing_invoice_service.py` — разделены причины неполных реквизитов ФФ и селлера; при двух причинах сервис сохраняет и возвращает обе.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/app/api/billing.py` — существующий ответ формирования и список проблем передают все актуальные причины, не скрывая вторую.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/tests/test_billing_invoice_service.py` — добавлены целевые случаи неполных профилей селлера, ФФ и отсутствия обоих профилей.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/tests/test_billing_invoice_api.py` — закреплён расширенный массив причин в ответе существующего endpoint.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/night/volna-9-recovery/cards/09-billing/DEV.md` — отчёт атома.

## Гейты

- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend && ruff check app/services/billing_invoice_service.py app/api/billing.py tests/test_billing_invoice_service.py tests/test_billing_invoice_api.py` — успешно, `All checks passed!`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend && mypy app/services/billing_invoice_service.py` — успешно, `Success: no issues found in 1 source file`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend && mypy app/api/billing.py` — не прошёл из-за двух уже существующих ошибок типов в `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/app/services/billing_configuration_service.py:200,203`; этот атом его не изменяет.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend && pytest -q tests/test_billing_invoice_service.py tests/test_billing_invoice_api.py` — успешно, `12 passed`.
- `back_guard.py` и `check_migrations.py` не запускались: новый route и миграция в атоме не добавлялись.

## Не реализовано

Нет. Изменение существующего API-ответа добавляет массив `reasons`, сохраняя прежние поля `reason` и `message` для обратной совместимости одиночной причины.
