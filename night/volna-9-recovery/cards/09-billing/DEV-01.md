# 09-billing · backend-dev · атом 1

## Что реализовано

- Эндпоинт `POST /operations/marketplace-unload-requests/{request_id}/cancel`: существующий маршрут при позднем вызове для документа `shipped` возвращает документ в статусе `shipped`; до физической отгрузки прежняя отмена в `cancelled` сохранена.
- Сервис `cancel_request`: для `shipped` записывает одну идемпотентную обратную финансовую запись и не запускает возврат складского остатка; статус `cancelled` теперь присваивается только в ветке отмены до отгрузки.

## Миграции

Нет.

## Тесты

- Расширен `test_cancel_shipped_unload_records_one_reversal_http`: после двух вызовов отмены ответы и повторно загруженный документ остаются `shipped`, снимок остатка совпадает со снимком после отгрузки, а в `BillingLedgerEntry` остаются одна исходная строка и ровно одна отрицательная `reversal` со снимком исходной ставки.
- Повторно проверен существующий `test_marketplace_unload_cancel_partial_distribution_restores_inventory`: отмена до отгрузки по-прежнему переводит документ в `cancelled` и возвращает собранный товар.

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/app/services/marketplace_unload_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/tests/test_marketplace_unload_completion.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/night/volna-9-recovery/cards/09-billing/DEV.md`

## Гейты

- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend && pytest -q tests/test_marketplace_unload_completion.py::test_cancel_shipped_unload_records_one_reversal_http` — `1 passed in 2.57s` после изменения.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend && pytest -q tests/test_marketplace_unload_completion.py::test_cancel_shipped_unload_records_one_reversal_http tests/test_marketplace_unload_and_discrepancy_acts.py::test_marketplace_unload_cancel_partial_distribution_restores_inventory` — `2 passed in 4.88s`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend && ruff check app/services/marketplace_unload_service.py tests/test_marketplace_unload_completion.py` — `All checks passed!`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend && mypy app/services/marketplace_unload_service.py` — изменённый модуль проверен, но команда завершилась с четырьмя ранее существующими ошибками в импортируемых `wildberries_credentials_service.py`, `fbs_stock_sync_service.py` и `fbs_warehouse_binding_service.py`; эти файлы не относятся к атому и не изменялись.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend && mypy --follow-imports=skip app/services/marketplace_unload_service.py` — `Success: no issues found in 1 source file`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing && git diff --check -- backend/app/services/marketplace_unload_service.py backend/tests/test_marketplace_unload_completion.py` — успешно, ошибок пробелов нет.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing && git add -- backend/app/services/marketplace_unload_service.py backend/tests/test_marketplace_unload_completion.py night/volna-9-recovery/cards/09-billing/DEV.md && git diff --cached --name-status && git diff --cached --check && git commit -m "fix(billing): preserve shipped unload after reversal"` — не выполнено: Git не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-3-09-billing1/index.lock` (`Operation not permitted`).
- `back_guard.py` не запускался: атом не добавляет и не меняет маршрут.
- `check_migrations.py` не запускался: миграций нет.

## Не реализовано

- Отдельный атом 2 про неизменяемость уже выставленного счёта и перенос сторно в следующий месяц не реализовывался: текущий запуск ограничен только атомом 1 из `FEATURES.md`.
- Новый UI, новый API-маршрут и новый пользовательский сценарий позднего сторно не добавлялись, как и требует граница атома.

## Находки

Нет.

## Блокеры

- Изменения локально реализованы и проверены, но не сохранены коммитом: права среды запрещают запись в Git index этого зарегистрированного worktree. Проверенного commit SHA нет.
