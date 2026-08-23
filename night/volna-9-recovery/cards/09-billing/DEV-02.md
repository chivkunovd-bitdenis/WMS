# 09-billing · backend-dev · атом 2

## Что реализовано

- Эндпоинты — новые маршруты не добавлялись; сценарий проверяет существующую цепочку `POST /operations/marketplace-unload-requests/{request_id}/ship` → `POST /billing/invoices/{seller_id}/{period}/form` → `POST /operations/marketplace-unload-requests/{request_id}/cancel` → формирование счёта следующего периода и чтение обоих счетов через `GET /billing/invoices/{invoice_id}`.
- Сервисы — бизнес-логика не изменялась; регрессия закрепляет совместную семантику `marketplace_unload_service` и `billing_invoice_service`: выставленный счёт хранит прежний снимок, а позднее сторно попадает единственной отрицательной строкой только в следующий календарный месяц по МСК.

## Миграции

Нет.

## Тесты

- Расширен `test_cancel_shipped_unload_records_one_reversal_http` (`S-31-TC-016`): исходная отгрузка зафиксирована 30 июня 2026 года в 23:30 МСК, после неё сформирован июньский счёт на `25,00`; сторно зафиксировано 1 июля в 00:15 МСК, после него сформирован июльский счёт только с отрицательной корректировкой `−25,00`.
- Тест сохраняет сумму и полную детализацию июньского счёта до сторно, повторно сверяет их после сторно и после повторной отмены, а также сохраняет и повторно сверяет июльский счёт.
- Проверено соответствие документов счетов конкретным ledger-записям: июнь содержит только исходное начисление, июль — только reversal; повторная отмена оставляет ровно две записи журнала и не меняет складской статус или остаток.
- Повторно выполнена относящаяся к атому 1 регрессия `test_marketplace_unload_cancel_partial_distribution_restores_inventory`: ранняя отмена до физической отгрузки сохраняет прежнюю семантику возврата остатка.

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/tests/test_marketplace_unload_completion.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/night/volna-9-recovery/cards/09-billing/DEV.md`

## Гейты

- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend && ruff check tests/test_marketplace_unload_completion.py && pytest -q tests/test_marketplace_unload_completion.py::test_cancel_shipped_unload_records_one_reversal_http` — первая попытка остановилась на `ruff`: найден и затем удалён неиспользуемый импорт `datetime.date`; `pytest` в этой связке не запускался.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend && ruff check tests/test_marketplace_unload_completion.py && pytest -q tests/test_marketplace_unload_completion.py::test_cancel_shipped_unload_records_one_reversal_http` — после исправления `All checks passed!`; `1 passed in 2.23s`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend && mypy tests/test_marketplace_unload_completion.py` — основной адресный запуск нашёл четыре ранее существующие ошибки в импортируемых сервисах и существующий `import-not-found` для соседнего тестового модуля; изменённые строки новых ошибок не дали.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend && MYPYPATH=tests mypy --follow-imports=skip tests/test_marketplace_unload_completion.py` — после изоляции импортов показал только семь ранее существующих `untyped-decorator` на `pytest.mark.asyncio` в этом файле.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend && MYPYPATH=tests mypy --follow-imports=skip --disable-error-code=untyped-decorator tests/test_marketplace_unload_completion.py` — `Success: no issues found in 1 source file`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend && pytest -q tests/test_marketplace_unload_completion.py::test_cancel_shipped_unload_records_one_reversal_http tests/test_marketplace_unload_and_discrepancy_acts.py::test_marketplace_unload_cancel_partial_distribution_restores_inventory` — выполнено дважды: `2 passed in 3.73s` и финально `2 passed in 3.80s`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing && git diff --check -- backend/tests/test_marketplace_unload_completion.py night/volna-9-recovery/cards/09-billing/DEV.md` — успешно, ошибок пробелов нет.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing && git add -- backend/tests/test_marketplace_unload_completion.py night/volna-9-recovery/cards/09-billing/DEV.md && git diff --cached --name-status && git diff --cached --check && git commit -m "test(billing): cover next-period reversal invoices"` — не выполнено: Git не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-3-09-billing1/index.lock` (`Operation not permitted`).
- `back_guard.py` не запускался: атом не добавляет и не меняет маршрут.
- `check_migrations.py` не запускался: миграций нет.

## Не реализовано

Нет: все пункты атома 2 и относящаяся к его файлу находка ревью реализованы буквально. Новый пользовательский сценарий, UI, API-маршрут и изменения бизнес-логики не добавлялись, поскольку они находятся за границами этого тестового атома.

## Находки

Нет.

## Блокеры

- Код, тест и артефакт локально реализованы и проверены, но среда запрещает запись в общий Git-каталог зарегистрированного worktree. Изменения не сохранены коммитом; проверенного commit SHA нет.
