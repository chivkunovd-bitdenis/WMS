# 09-billing — backend-dev · ремонт атома 7

## Что реализовано

- Эндпоинт: существующий `POST /operations/marketplace-unload-requests/{request_id}/cancel` теперь передаёт исполнителя отмены и идемпотентно отменяет уже финальную marketplace-отгрузку.
- Сервис: `record_operational_reversal` находит исходное начисление по tenant и складскому факту, сохраняет отдельную отрицательную строку с тем же снимком тарифа, единицей и количеством и защищён от дубля уникальностью `reversal_of_id` и savepoint (вложенной транзакцией).
- Сервис: `cancel_request` разделяет предфинальную отмену и позднюю финансовую корректировку. Для `shipped` физически отгруженный товар не возвращается на склад; создаётся сторно и документ переходит в `cancelled`. Повторная отмена возвращает уже достигнутое состояние и не создаёт вторую строку.

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/app/api/marketplace_unload_requests.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/app/services/billing_invoice_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/app/services/billing_ledger_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/app/services/marketplace_unload_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/app/services/marketplace_unload_status.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/tests/test_billing_ledger_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/tests/test_marketplace_unload_completion.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/night/volna-9-recovery/cards/09-billing/DEV.md`

## Миграции

Нет: схема базы данных не менялась.

## Тесты

- `backend/tests/test_billing_ledger_service.py::test_operational_reversal_preserves_snapshot_and_is_idempotent` — отрицательная строка сохраняет снимок исходной ставки, количество и исполнителя; повтор возвращает существующее сторно.
- `backend/tests/test_marketplace_unload_completion.py::test_cancel_shipped_unload_records_one_reversal_http` (`S-31-TC-016`) — живой HTTP-путь завершает отгрузку, отменяет её, повторяет отмену и подтверждает ровно одну положительную и одну отрицательную строку журнала с правильными суммами и исполнителем.
- Повторно пройдены `test_ship_unload_without_discrepancy_http` и `test_marketplace_unload_cancel_partial_distribution_restores_inventory`: обычная финализация и прежняя предфинальная отмена не сломаны.

## Гейты

- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend && ruff check app/services/billing_ledger_service.py app/services/billing_invoice_service.py app/services/marketplace_unload_status.py app/services/marketplace_unload_service.py app/api/marketplace_unload_requests.py tests/test_billing_ledger_service.py tests/test_marketplace_unload_completion.py` — PASS: `All checks passed!`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend && mypy app/services/billing_ledger_service.py app/services/billing_invoice_service.py app/services/marketplace_unload_status.py app/services/marketplace_unload_service.py app/api/marketplace_unload_requests.py` — внешний FAIL: четыре ранее существующие ошибки только в импортируемых соседних `wildberries_credentials_service.py`, `fbs_stock_sync_service.py` и `fbs_warehouse_binding_service.py`; изменённые файлы в выводе ошибок отсутствуют.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend && mypy --follow-imports=skip app/services/billing_ledger_service.py app/services/billing_invoice_service.py app/services/marketplace_unload_status.py app/services/marketplace_unload_service.py` — PASS: `Success: no issues found in 4 source files`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend && pytest -q tests/test_billing_ledger_service.py tests/test_marketplace_unload_completion.py::test_cancel_shipped_unload_records_one_reversal_http` — PASS: `6 passed in 2.41s`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend && pytest -q tests/test_marketplace_unload_completion.py::test_ship_unload_without_discrepancy_http tests/test_marketplace_unload_and_discrepancy_acts.py::test_marketplace_unload_cancel_partial_distribution_restores_inventory` — PASS: `2 passed in 4.48s`.
- `python3 scripts/ci/back_guard.py` — не применим: новый маршрут не добавлялся.
- `python3 scripts/ci/check_migrations.py` — не применим: миграция не добавлялась.
- Полный backend `pytest`, `ruff check .` и `mypy .` не запускались согласно ограничению атомарной проверки.

## Не реализовано

- Для завершённой приёмки в текущем backend нет рабочего перехода отмены из `done`; новый маршрут или новый складской процесс контракт атома не вводит. Начисление при первом `done` остаётся прежним и не дублируется. Универсальный сервис сторно готов к подключению, когда такой доменный переход появится отдельным контрактом.
- Находки ревью 1–5, 7 и 8 относятся к read-model/API счетов, storage-barrier, миграционному графу и frontend; эти соседние атомы не менялись.

## Блокеры

- Git-сохранение заблокировано правами среды: команда `git add ... && git commit -m "fix(billing): reverse cancelled final unload charges"` завершилась `fatal: Unable to create '/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-3-09-billing1/index.lock': Operation not permitted`. Код и артефакт находятся в постоянном зарегистрированном worktree, но не добавлены в индекс и не сохранены коммитом; проверенного SHA нет.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных и боевой прод не читались и не затрагивались.
