# 09-billing — backend-dev · rework атома 3 / 09-A

## Что реализовано

- Эндпоинты: нет; атом финансового фундамента не добавляет HTTP-маршруты.
- Сервисы: нет; атом закрепляет модели и миграционную цепочку общего финансового ядра.
- Миграционные идентификаторы billing-цепочки заменены на уникальные для карточки 09: `20260822_09a → 20260822_09b → 20260822_09c`. Это устраняет коллизии с ревизиями `0094` и `0096` соседних карточек при интеграции волны.
- Адресный тест миграции теперь проверяет единственную вершину, порядок всей billing-цепочки и то, что 09-A создаёт только `billing_profiles`, `billing_tariff_versions` и `billing_ledger_entries`.
- Тест неизменяемого журнала подтверждает, что второе начисление одного исходного события и второе сторно отклоняются базой, а запись исходного начисления после сторно остаётся неизменной.

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/alembic/versions/20260822_09a_billing_financial_core.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/alembic/versions/20260822_09b_billing_invoices.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/alembic/versions/20260822_09c_billing_activation_date.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/tests/test_billing_models.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/tests/test_billing_financial_core_migration.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/night/volna-9-recovery/cards/09-billing/DEV.md`

Удалённые прежние имена тех же миграций:

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/alembic/versions/20260822_0094_billing_financial_core.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/alembic/versions/20260822_0095_billing_invoices.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/alembic/versions/20260822_0096_billing_activation_date.py`

## Миграции

- `20260822_09a_billing_financial_core.py` (`revision = 20260822_09a`) — добавляет единый набор таблиц профилей, версионных тарифов и неизменяемого журнала начислений/сторно; поддерживает `document`, `item`, `liter_day`, `storage_liter_day` и `storage_measurement` на уровне модели данных без параллельных финансовых таблиц.
- `20260822_09b_billing_invoices.py` (`revision = 20260822_09b`) — существующая добавляющая миграция счетов и проблем запуска; в этом атоме изменены только её идентификатор и ссылка на предыдущую ревизию.
- `20260822_09c_billing_activation_date.py` (`revision = 20260822_09c`) — существующая добавляющая миграция даты включения биллинга; в этом атоме изменены только её идентификатор и ссылка на предыдущую ревизию.

## Тесты

- `backend/tests/test_billing_models.py` — проверяет частичные уникальные индексы, запрет второго начисления для одного source event, запрет второго сторно и неизменность исходного charge после сторно.
- `backend/tests/test_billing_financial_core_migration.py` — проверяет единственный Alembic head, непрерывный порядок `09a → 09b → 09c`, ровно три таблицы финансового ядра в 09-A, уникальность исходного события и внешний ключ сторно с `ON DELETE RESTRICT`.

## Гейты

- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend && ruff check app/models/billing.py alembic/versions/20260822_09a_billing_financial_core.py alembic/versions/20260822_09b_billing_invoices.py alembic/versions/20260822_09c_billing_activation_date.py tests/test_billing_models.py tests/test_billing_financial_core_migration.py` — PASS: `All checks passed!`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend && mypy app/models/billing.py` — PASS: `Success: no issues found in 1 source file`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend && pytest -q tests/test_billing_models.py tests/test_billing_financial_core_migration.py` — PASS: `5 passed, 2 warnings in 0.33s`; оба предупреждения относятся к устаревающей настройке Alembic `path_separator`, не к поведению атома.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend && alembic heads` — PASS: `20260822_09c (head)`.
- `python3 scripts/ci/back_guard.py` — не применим: новый роут не добавлялся.
- `python3 scripts/ci/check_migrations.py` — не запускался: атом не добавляет миграцию, а исправляет идентификаторы существующей добавляющей цепочки; кроме того, этого файла в рабочей копии нет.

Полный `pytest`, `ruff check .` и `mypy .` не запускались согласно ограничению атомарной проверки.

## Не реализовано

- Находки 1–6 и 8 из `REVIEW.md` относятся к API, invoice/ledger-сервисам и frontend, а не к моделям и миграции атома 09-A; эти слои не изменялись.
- Схема таблиц миграций 09-B и даты активации не менялась: для устранения коллизий достаточно уникальных Alembic revision ID и непрерывных `down_revision` внутри billing-ветки.

## Блокеры

- Сохранение отдельным Git-коммитом невозможно в текущей среде: `git add` завершился с `fatal: Unable to create '/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-3-09-billing1/index.lock': Operation not permitted`. Исходники и этот артефакт записаны в разрешённую рабочую копию, но Git index и SHA не созданы.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных и боевой прод не читались и не затрагивались.
