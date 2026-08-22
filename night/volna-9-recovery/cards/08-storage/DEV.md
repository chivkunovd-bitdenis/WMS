# DEV · 08-storage · атом 7

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/app/services/storage_statement_service.py` — публикация использует контракт общего `BillingLedgerEntry` из 09-A (`tariff_version_id`, `rate`, `source`); нулевой statement получает единственный уникальный source id самого документа, а выборка ledger ограничена source ids именно этого statement.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/app/api/storage.py` — фиксированный и повторно печатаемый расчёт отдаёт имя селлера и склада, SKU, артикул, объём, источник габаритов, литро-дни, снимок ставки, сумму и дату фиксации; нулевой документ возвращает пустой состав SKU вместо ошибки `zip(..., strict=True)`.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/tests/test_storage_statement_service.py` — целевые проверки уникального source id нулевого statement, источников обычных строк и безопасной повторной печати нулевого документа.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/night/volna-9-recovery/cards/08-storage/DEV.md` — отчёт атома.

## Гейты

- `ruff check backend/app/services/storage_statement_service.py backend/app/api/storage.py backend/tests/test_storage_statement_service.py` — успешно: `All checks passed!`.
- `cd backend && pytest -q tests/test_storage_statement_service.py` — успешно: `3 passed in 0.01s`.
- `cd backend && mypy app/services/storage_statement_service.py app/api/storage.py` — не пройден: в этой рабочей копии отсутствует обязательный внешний модуль `app.models.billing` из 09-A; также mypy сообщает три существующие ошибки вне атома в `wildberries_credentials_service.py`, `fbs_stock_sync_service.py` и `fbs_warehouse_binding_service.py`.
- `python3 scripts/ci/back_guard.py` — неприменимо: атом не добавляет новый маршрут; файла `scripts/ci/back_guard.py` в данной рабочей копии также нет.
- `python3 scripts/ci/check_migrations.py` — неприменимо: атом не добавляет миграцию; файла `scripts/ci/check_migrations.py` в данной рабочей копии также нет.
- `git diff --check` — успешно, пробеловых ошибок нет.

## Не реализовано

- Разбиение одного агрегированного `StorageMeasurement.liter_days` между несколькими тарифными интервалами внутри месяца: текущая модель измерения не хранит посуточное или интервальное распределение литро-дней, поэтому точный расчёт новой ставки с середины месяца невозможно получить из этого агрегата без изменения контракта измерений. Текущий сервис использует действующую на начало периода версию общего тарифа 09-A.
- Полный интеграционный сценарий фиксации и конкурентных запросов не запускается до появления в этой ветке обязательных моделей 09-A `BillingTariffVersion` и `BillingLedgerEntry`. Секреты, ключи, токены, `.env` и кабинеты учётных данных не читались и не использовались.
