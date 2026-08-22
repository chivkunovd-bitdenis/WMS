# DEV · 07-reporting · атом 7

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend/app/services/reporting_service.py` — серверная пагинация по 50 строк, белый список сортировок, исключение внутренних transfer без фильтра склада и точечный `integrity_error` для неполных transfer-пар.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend/app/api/reports.py` — параметры разрешённой сортировки для `GET /reports/inventory`.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend/tests/test_reports_inventory.py` — API-покрытие страниц, обеих группировок, поиска по четырём полям, служебного склада, transfer и неполной пары.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/night/volna-9-recovery/cards/07-reporting/DEV.md` — отчёт атома.

## Гейты

- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend && ruff check app/services/reporting_service.py app/api/reports.py tests/test_reports_inventory.py` — `All checks passed!`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend && mypy app/services/reporting_service.py app/api/reports.py` — `Success: no issues found in 2 source files`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend && pytest -q tests/test_reports_inventory.py` — `3 passed`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting && python3 scripts/ci/back_guard.py` — не выполнен: файла `scripts/ci/back_guard.py` в этой рабочей копии нет.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting && python3 scripts/ci/check_migrations.py` — не выполнен: файла `scripts/ci/check_migrations.py` в этой рабочей копии нет; миграций атом не добавляет.
- `git diff --check` — будет проверен перед коммитом.

## Не реализовано

- Находки review по экрану, сводке и CSV не входят в атом 7 и не менялись: это соседние frontend-атомы, атом 6 и атом 8 соответственно.
- Секреты, ключи, токены, `.env` и кабинеты учётных данных не читались.
