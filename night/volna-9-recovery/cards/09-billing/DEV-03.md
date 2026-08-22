# 09-billing — backend-dev 09-A

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/app/models/billing.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/app/models/__init__.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/alembic/versions/20260822_0094_billing_financial_core.py`

Добавлены `BillingProfile`, `BillingTariffVersion` и `BillingLedgerEntry`. Профили и тарифы
tenant-изолированы, тарифы поддерживают `document`, `item`, `liter_day`; для хранения сохраняются
контрактные `service_code='storage_liter_day'` и `source='storage_measurement'`. Ledger запрещает
повторное начисление одного исходного события уникальностью `(tenant_id, source_type, source_id)`;
сторно хранит `reversal_of_id` и не имеет операции изменения исходной строки.

## Гейты

- `ruff`: PASS для изменённого `backend/app/models/billing.py`; полный запуск репозитория BLOCKED существующими ошибками вне карточки.
- `mypy`: PASS для `backend/app/models/billing.py` (`Success: no issues found in 1 source file`).
- `pytest`: запущен, но остановлен после частичного выполнения из-за длительности полного набора; итоговый PASS не подтверждён.
- `back_guard.py`: BLOCKED — файл `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/scripts/ci/back_guard.py` отсутствует.
- `check_migrations.py`: BLOCKED — файл `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/scripts/ci/check_migrations.py` отсутствует.
- `compileall`: PASS для новой модели.

## Не реализовано

- API, сервисы, обработчики операционных начислений и счета не реализованы: они относятся к следующим атомарным кускам 09-billing и не входят в 09-A.
- Автоматическая запретительная защита UPDATE/DELETE ledger на уровне БД не добавлялась: текущий контракт фиксирует неизменяемость через модель данных и ссылку сторно; отдельный writer/сервис будет добавлен в следующем backend-атоме.

## Находки

Секреты, ключи, токены, `.env` и кабинеты учётных данных не читались и не затрагивались. Боевой прод не трогался.
