# 09-billing — атом 7: единая нумерация счетов

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/app/services/billing_invoice_service.py` — выпуск счёта получает номер через `document_number_service`, а не выводит его из UUID селлера.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/app/services/document_number_service.py` — добавлен тип документа `invoice` с префиксом `СЧЕТ`, чтобы общий сервис мог выделять номера счетам отдельно от складских документов.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/tests/test_billing_invoice_service.py` — добавлен сценарий двух селлеров одного месяца: сервис выдаёт разные непрозрачные номера и повторно возвращает уже созданный счёт без нового номера.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/night/volna-9-recovery/cards/09-billing/DEV.md` — отчёт атома.

## Миграции

Нет: используется существующая таблица последовательностей документов.

## Тесты

- `test_form_invoice_uses_shared_document_number_for_each_seller` проверяет общую нумерацию для двух селлеров и идемпотентный повторный выпуск.

## Гейты

- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend && ruff check app/services/billing_invoice_service.py app/services/document_number_service.py tests/test_billing_invoice_service.py` — успешно, `All checks passed!`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend && mypy app/services/billing_invoice_service.py app/services/document_number_service.py` — успешно, `Success: no issues found in 2 source files`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend && pytest -q tests/test_billing_invoice_service.py` — успешно, `9 passed in 0.13s`.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/scripts/ci/back_guard.py` и `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/scripts/ci/check_migrations.py` не запускались: атом не добавляет маршрут или миграцию.

## Не реализовано

Нет: все пункты атома реализованы. Номер получает дата выдачи, как у существующего сервиса нумерации документов; период счёта не содержит идентификатор селлера.

## Блокеры

Git-коммит не создан: `git add` не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-3-09-billing1/index.lock` из-за ограничения записи вне разрешённого worktree. Реализация существует в рабочем дереве, но без commit SHA не может считаться сохранённой в Git.
