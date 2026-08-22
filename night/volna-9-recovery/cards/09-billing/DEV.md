# 09-billing — backend-dev, rework атома 7

## Изменённые файлы

- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/app/models/tenant.py — добавлено nullable-поле `billing_enabled_from`; пустое значение оставляет биллинг выключенным для существующего tenant.
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/alembic/versions/20260822_0096_billing_activation_date.py — добавляющая миграция даты включения биллинга.
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/app/services/billing_configuration_service.py — первый явно сохранённый тариф фиксирует дату включения tenant равной `valid_from`.
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/app/services/billing_ledger_service.py — до даты включения не создаёт ни тарифицированную, ни `unpriced` строку; с даты включения сохраняет прежнее атомарное идемпотентное поведение.
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/tests/test_billing_ledger_service.py — покрыт пропуск финального факта до даты включения.
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/tests/test_billing_configuration_service.py — покрыта фиксация даты включения первым тарифом.

## Эндпоинты и сервисы

- Эндпоинты: нет; существующие финальные пути приёмки и ФФ→МП-отгрузки продолжают использовать `record_operational_charge`.
- Сервисы: `billing_ledger_service.record_operational_charge` применяет границу `billing_enabled_from`; `billing_configuration_service.create_tariff` записывает явный старт из первого выбранного `valid_from`.

## Миграции

- `20260822_0096_billing_activation_date` — добавляет nullable-колонку `tenants.billing_enabled_from`, без удаления или изменения существующих данных.

## Тесты

- `test_operational_charge_before_billing_activation_is_not_recorded` — старый финальный факт не создаёт ledger-запись.
- `test_first_tariff_explicitly_activates_billing_from_its_start_date` — первый тариф задаёт дату начала учёта.

## Гейты

- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend && ruff check app/models/tenant.py app/services/billing_ledger_service.py app/services/billing_configuration_service.py tests/test_billing_ledger_service.py tests/test_billing_configuration_service.py alembic/versions/20260822_0096_billing_activation_date.py` — PASS.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend && mypy app/models/tenant.py app/services/billing_ledger_service.py app/services/billing_configuration_service.py` — PASS, 3 source files.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend && pytest -q tests/test_billing_ledger_service.py tests/test_billing_configuration_service.py` — PASS, 10 passed.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing && python3 scripts/ci/back_guard.py` — не выполнен: файла `scripts/ci/back_guard.py` в этой рабочей копии нет.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing && python3 scripts/ci/check_migrations.py` — не выполнен: файла `scripts/ci/check_migrations.py` в этой рабочей копии нет.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend && alembic heads` — PASS, единственный head `20260822_0096`.
- `git diff --check` — PASS.

## Не реализовано

- Находки ревью по read-model, счетам, поздней тарификации, storage-barrier, сторно, API и UI не относятся к атому 7 и его не меняли.
- Перекрёстная корректировка базовой миграционной цепочки из находки 12 не относится к этому атому; новая миграция продолжает текущую единственную цепочку `20260822_0095 → 20260822_0096`.

## Блокеры

Git не позволяет создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-3-09-billing1/index.lock`: `Operation not permitted`. Поэтому commit и проверенный SHA не получены; изменения существуют только в рабочем дереве. Секреты, ключи, токены, `.env`, кабинеты учётных данных и боевой production не читались и не затрагивались.
