# 09-billing — backend-dev, атом 1

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/app/api/billing.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/app/services/billing_configuration_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/tests/test_billing_configuration_api.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/night/volna-9-recovery/cards/09-billing/DEV.md`

## Реализовано

- `POST /billing/tariffs`: входное поле `amount` остаётся суммой в рублях с двумя знаками, а ответ и `GET /billing/tariffs` возвращают целые копейки.
- `create_tariff`: до записи преобразует рубли в `int` копеек; дооценка ранее неоценённых строк этого же сервиса также записывает целые копейки.

## Миграции

Нет.

## Тесты

- `test_billing_configuration_api_validates_profiles_tariffs_and_tenant_boundary`: `0.00` и `45.00` создают тарифы с `0` и `4500` копеек в HTTP-ответах и базе; отрицательная и трёхзнаковая дробная ставки отклоняются валидацией.

## Гейты

- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend && ruff check app/api/billing.py app/services/billing_configuration_service.py tests/test_billing_configuration_api.py` — пройдено (`All checks passed!`).
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend && mypy app/api/billing.py app/services/billing_configuration_service.py` — пройдено (`Success: no issues found in 2 source files`).
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend && pytest -q tests/test_billing_configuration_api.py` — пройдено (`1 passed`).
- `back_guard.py` и `check_migrations.py` не запускались: атом не добавляет роут и миграцию.

## Не реализовано

- Атомы 2–7 из `FEATURES.md` не затрагивались. Изменение дооценки внутри `create_tariff` ограничено устранением связанной находки ревью о передаче `Decimal` в целочисленные поля.
- Отдельный Git-коммит не создан: `git add` не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-3-09-billing1/index.lock` (`Operation not permitted`). Поэтому изменения существуют только в рабочем дереве и нуждаются в сохранении после восстановления доступа к Git-метаданным.

## Блокеры

Нет.
