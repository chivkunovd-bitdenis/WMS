# Backend-dev · 07-reporting · атом 1 · повторная доработка

## Что реализовано

- Эндпоинты: существующие `GET /reports/overview`, `GET /reports/inventory` и `GET /reports/inventory/export.csv` теперь отвечают `403 forbidden` сотруднику ФФ с `cells=true` и `inventory=false`; администратор ФФ, сотрудник с `inventory=true` и селлер с действующим `can_products` сохраняют доступ.
- Сервисы: изменён общий dependency `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend/app/api/deps.py::assert_inventory_read_access`; для отчётов он принимает у сотрудника ФФ только `inventory`, не право ячеек.

## Миграции

Нет.

## Тесты

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend/tests/test_reports_inventory.py::test_reports_require_inventory_for_ff_staff_but_keep_allowed_roles` создаёт сотрудника ФФ с `cells=true, inventory=false` и проверяет `403` с `detail=forbidden` для сводки, строк и CSV. В том же сценарии с непустым срезом закреплён `200` для администратора ФФ, сотрудника с `inventory=true` и селлера.

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend/app/api/deps.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend/tests/test_reports_inventory.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/night/volna-9-recovery/cards/07-reporting/DEV.md`

## Гейты

- ЗЕЛЁНЫЙ: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend && ruff check app/api/deps.py tests/test_reports_inventory.py` — `All checks passed!`, код завершения 0.
- ЗЕЛЁНЫЙ: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend && mypy --follow-imports=silent app/api/deps.py tests/test_reports_inventory.py` — `Success: no issues found in 2 source files`, код завершения 0. Режим `silent` проверяет затронутые модули, не включая прежние ошибки транзитивных импортов вне атома.
- ЗЕЛЁНЫЙ: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend && pytest -q tests/test_reports_inventory.py` — `5 passed in 6.77s`, код завершения 0.
- ЗЕЛЁНЫЙ: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting && git diff --check` — ошибок формата diff нет, код завершения 0.
- `python3 scripts/ci/back_guard.py` не запускался: новый роут не добавлялся.
- `python3 scripts/ci/check_migrations.py` не запускался: миграция не добавлялась.
- Полные `pytest`/`pytest -q` без путей, `ruff check .` и `mypy .` не запускались: границы атома запрещают полный backend-регресс.

## Не реализовано

- Нет: атом из `FEATURES.md` и серверная находка №1 из `REVIEW.md` реализованы буквально. Находка №2 относится к маршрутизации самостоятельного frontend-приложения селлера и не менялась этой backend-ролью.

## Блокеры

- Сохранение в Git не выполнено: команда `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting && git add backend/app/api/deps.py backend/tests/test_reports_inventory.py night/volna-9-recovery/cards/07-reporting/DEV.md && git diff --cached --check && git commit -m "fix(reports): require inventory permission"` завершилась с кодом 128, потому что sandbox запретил создание `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-1-07-reporting1/index.lock` (`Operation not permitted`). Изменения остаются в рабочем дереве без нового commit SHA; чужие файлы не индексировались.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных, production `194.87.96.144` и живой кабинет Wildberries не читались и не затрагивались.
