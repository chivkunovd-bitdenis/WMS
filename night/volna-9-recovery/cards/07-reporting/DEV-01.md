# Backend-dev · 07-reporting · атом 1 · повторная доработка

## Что реализовано

- Эндпоинты: существующие `GET /reports/overview`, `GET /reports/inventory` и `GET /reports/inventory/export.csv` отвечают `403 forbidden` сотруднику ФФ с `cells=true` и `inventory=false`; администратор ФФ, сотрудник с `inventory=true` и селлер с действующим `can_products` сохраняют доступ.
- Сервисы: `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend/app/api/deps.py::assert_inventory_read_access` принимает у сотрудника ФФ для отчётов только `inventory`, без права ячеек.

## Миграции

Нет.

## Тесты

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend/tests/test_reports_inventory.py::test_reports_require_inventory_for_ff_staff_but_keep_allowed_roles` создаёт сотрудника ФФ с `cells=true, inventory=false` и проверяет `403` с `detail=forbidden` для сводки, строк и CSV. В том же сценарии закреплён `200` для администратора ФФ, сотрудника с `inventory=true` и селлера.

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend/app/api/deps.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend/tests/test_reports_inventory.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/night/volna-9-recovery/cards/07-reporting/DEV.md`

## Гейты

- ЗЕЛЁНЫЙ: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend && ruff check app/api/deps.py tests/test_reports_inventory.py` — `All checks passed!`, код завершения 0.
- ЗЕЛЁНЫЙ: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend && mypy --follow-imports=silent app/api/deps.py tests/test_reports_inventory.py` — `Success: no issues found in 2 source files`, код завершения 0.
- ЗЕЛЁНЫЙ: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend && pytest -q tests/test_reports_inventory.py` — `5 passed in 18.03s`, код завершения 0.
- ЗЕЛЁНЫЙ: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting && git diff --check` — ошибок формата diff нет, код завершения 0.
- `python3 scripts/ci/back_guard.py` не запускался: новый роут не добавлялся.
- `python3 scripts/ci/check_migrations.py` не запускался: миграция не добавлялась.
- Полные `pytest`/`pytest -q` без путей, `ruff check .` и `mypy .` не запускались: границы атома запрещают полный backend-регресс.

## Не реализовано

- Нет: атом из `FEATURES.md` и серверная находка №1 из `REVIEW.md` реализованы буквально. Находка №2 относится к маршрутизации самостоятельного frontend-приложения селлера и не менялась этой backend-ролью.

## Блокеры

- Обновлённый отчёт не удалось сохранить отдельным commit: команда `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting && git add night/volna-9-recovery/cards/07-reporting/DEV.md && git diff --cached --check && git commit -m "docs(reporting): record backend atom gates"` завершилась с кодом 128, потому что sandbox запретил создание `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-1-07-reporting1/index.lock` (`Operation not permitted`). Реализация и тесты атома уже сохранены в commit `cb8e509aa148`; обновление `DEV.md` остаётся в рабочем дереве.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных, production `194.87.96.144` и живой кабинет Wildberries не читались и не затрагивались.
