## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/app/api/billing.py` — GET начислений и счетов принимают период `YYYY-MM`, значение `seller_id=all`, фильтры, возвращают оболочки экрана и отдельные блокирующие причины; формирование проверяет tenant через сервис.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/app/services/billing_invoice_service.py` — проверена принадлежность селлера tenant, storage-barrier опирается на опубликованные `storage_measurement`, а строки счёта содержат неизменяемые дату и номер исходного факта.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/app/services/billing_configuration_service.py` — добавление покрывающей ставки ретарифицирует только ранее неоценённые подходящие записи ledger.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/tests/test_billing_invoice_service.py` — обновлены сценарии формирования с проверкой tenant-принадлежности до поиска счёта.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/tests/test_billing_configuration_service.py` — обновлены моки потока ретарификации.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/docs/blockers/S-31.md` — зафиксированы объяснения `unpriced`, `missing_profile` и `storage_period_not_closed`.

## Гейты

- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend && ruff check app/services/billing_invoice_service.py app/services/billing_configuration_service.py app/api/billing.py tests/test_billing_invoice_service.py tests/test_billing_configuration_service.py` — зелёный, `All checks passed!`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend && mypy app/services/billing_invoice_service.py app/services/billing_configuration_service.py app/api/billing.py` — зелёный, `Success: no issues found in 3 source files`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend && pytest -q tests/test_billing_invoice_service.py tests/test_billing_configuration_service.py tests/test_billing_configuration_api.py tests/test_billing_ledger_service.py` — зелёный, `13 passed`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing && python3 scripts/ci/back_guard.py` — не выполнен: файла `scripts/ci/back_guard.py` в рабочей копии нет.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing && python3 scripts/ci/check_migrations.py` — не выполнен: файла `scripts/ci/check_migrations.py` в рабочей копии нет; миграции в этом rework не менялись.
- `git diff --check` — зелёный.

## Не реализовано

- Привязка `record_reversal` к конкретному пути отмены складского документа не внесена: в атоме не назван допустимый production-путь отмены, а новый маршрут создал бы неописанный контрактом способ менять финансовую историю.
- API возвращает блокирующие причины отдельным массивом `issues`; текущий экран должен потребить этот массив. Его изменение вне роли `backend-dev`.
- Миграция финансового ядра не менялась: обязательный предшественник 07-A отсутствует в этой рабочей копии, а изменение `down_revision` без него создало бы невалидную цепочку.
