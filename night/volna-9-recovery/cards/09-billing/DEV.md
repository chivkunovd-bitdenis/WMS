# 09-billing — backend-dev, атом 4: API реквизитов и версионных тарифов

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/app/services/billing_configuration_service.py` — нормализация обязательных банковских полей, единая tenant-проверка селлера и блокировка tenant/цепочки тарифов при создании новой версии; конфликт уникальности преобразуется в понятную доменную ошибку.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/app/api/billing.py` — чужой seller-profile не раскрывается, а конкурентный конфликт тарифа возвращает понятный HTTP 400 вместо 500.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/tests/test_billing_configuration_service.py` — проверка, что пробелы не проходят как обязательные банковские реквизиты.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/tests/test_billing_configuration_api.py` — HTTP-сценарий: валидный профиль и нулевая ставка, пробельные реквизиты, чужой селлер и конфликт версии.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/night/volna-9-recovery/cards/09-billing/DEV.md` — этот отчёт.

## Гейты

- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend && ruff check app/services/billing_configuration_service.py app/api/billing.py tests/test_billing_configuration_service.py tests/test_billing_configuration_api.py` — пройдено: `All checks passed!`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend && mypy app/services/billing_configuration_service.py app/api/billing.py` — пройдено: `Success: no issues found in 2 source files`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend && pytest -q tests/test_billing_configuration_service.py tests/test_billing_configuration_api.py` — пройдено: `6 passed`.
- `git diff --check` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing` — пройдено, вывода нет.
- `python3 scripts/ci/back_guard.py` — неприменим: в атоме не добавлялся новый маршрут; файла `scripts/ci/back_guard.py` в этой рабочей копии нет.
- `python3 scripts/ci/check_migrations.py` — неприменим: миграция в атоме не добавлялась; файла `scripts/ci/check_migrations.py` в этой рабочей копии нет.

## Не реализовано

- Находки ревью по read-model начислений и счетов, формированию/сторно счетов, storage-barrier, дате включения биллинга, миграционной линии, frontend e2e и `docs/blockers/S-31.md` не относятся к атомарному API-контуру реквизитов и версионных тарифов; этот атом их не изменяет.
- Автоматическая переоценка уже записанных `BillingLedgerEntry` без ставки после добавления тарифа требует изменения ledger/invoice-контура и не выполнялась в этом атоме, чтобы не переписывать финансовую историю за пределами утверждённого шага.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных и боевой прод не читались и не затрагивались.
