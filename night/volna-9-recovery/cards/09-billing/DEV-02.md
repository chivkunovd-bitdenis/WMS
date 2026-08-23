# 09-billing — backend-dev, атом 2

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/tests/test_billing_configuration_api.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/night/volna-9-recovery/cards/09-billing/DEV.md`

## Реализовано

- `POST /billing/tariffs`: покрывающий тариф дооценивает ранее неоценённые строки `BillingLedgerEntry` для документной, поштучной и литр-дневной услуг целыми копейками.
- `create_tariff`: существующая реализация закрепляет снимок версии тарифа, ставку и итог без передачи `Decimal` в поля `rate` и `amount`; этот атом добавляет регрессионную проверку поведения после `flush`.

## Миграции

Нет.

## Тесты

- `test_creating_covering_tariffs_reprices_unpriced_entries_in_kopecks`: создаёт неоценённые строки журнала, добавляет покрывающие тарифы через API и проверяет после `flush` снимок тарифа, целые `rate`/`amount`, нормализацию документного количества до одного и точные количества для `item` и `liter_day`.

## Гейты

- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend && ruff check app/services/billing_configuration_service.py tests/test_billing_configuration_api.py` — пройдено (`All checks passed!`).
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend && mypy app/services/billing_configuration_service.py` — пройдено (`Success: no issues found in 1 source file`).
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend && pytest -q tests/test_billing_configuration_api.py` — пройдено (`2 passed`).
- `back_guard.py` и `check_migrations.py` не запускались: атом не добавляет маршрут или миграцию.

## Не реализовано

- Следующие атомы `FEATURES.md` не затрагивались.
- Git-коммит не создан: `git add` не может создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-3-09-billing1/index.lock` (`Operation not permitted`). Изменения остаются в рабочем дереве и не защищены коммитом.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных и боевой прод не читались и не затрагивались.
