# DEV · 07-reporting · атом 6

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend/app/services/reporting_service.py` — `GET /reports/overview`: московская дневная агрегация, сопоставленная серия прошлого периода, пустая серия без искусственных нулей, свежесть Wildberries и предупреждения legacy-истории.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend/app/api/reports.py` — служебное предупреждение legacy-истории доступно только администратору ФФ; селлер получает только предупреждение о свежести внешнего источника.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend/tests/test_reports_overview.py` — API-покрытие 367 дней, аутентификации, полуоткрытой верхней границы, Moscow-дня, transfer-исключения, физического остатка, нулевой базы сравнения и принудительного seller scope.

## Гейты

- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend && ruff check app/services/reporting_service.py app/api/reports.py tests/test_reports_overview.py` — `All checks passed!`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend && mypy app/services/reporting_service.py app/api/reports.py` — `Success: no issues found in 2 source files`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend && pytest -q tests/test_reports_overview.py` — `4 passed in 3.34s`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting && python3 scripts/ci/back_guard.py` — не запущен: файла `scripts/ci/back_guard.py` в этой рабочей копии нет.
- `git diff --check` — без ошибок.
- `check_migrations.py` не применим: миграция в этом атоме не добавлялась.

## Не реализовано

- Замечания ревью по таблице transfer-пар, CSV и миграционному backfill не менялись: это атомы 7, 8 и 07-A соответственно, вне границы текущего `GET /reports/overview`.
- Клиентская передача закрытой даты как полуоткрытой верхней границы, московские пресеты, отображение линии сравнения и предупреждений не менялись: это frontend-слой.
