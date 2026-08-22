# DEV · 07-reporting · атом 7 · переделка по review

## Что реализовано

- `GET /reports/inventory` — подтверждена постраничная выдача по товарам и операциям с поиском, разрешёнными сортировками, исключением служебных складов и отдельными сторонами transfer при выборе склада.
- `reporting_service.build_inventory_report` — подтверждены московские календарные границы для offset-less дат, человекопонятные названия операций и `integrity_error` для неполной либо повреждённой transfer-пары без эвристического достраивания.

## Миграции

Нет.

## Тесты

- В `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend/tests/test_reports_inventory.py` добавлен API-сценарий московской границы суток: запись `2026-07-31 22:30 UTC` входит в локальный день 1 августа, а запись ровно `2026-08-01 21:00 UTC` исключается верхней границей.
- Тем же файлом проверены обе группировки, русское название операции «Приёмка», страницы по 50 агрегатов, поиск по названию/артикулу/SKU/ШК, отсутствие служебных складов, отдельная transfer-строка и ошибка целостности для одиночной и повреждённой пары из двух `stock_transfer_out`.

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend/tests/test_reports_inventory.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/night/volna-9-recovery/cards/07-reporting/DEV.md`

## Гейты

- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend && ruff check app/services/reporting_service.py app/api/reports.py tests/test_reports_inventory.py` — `All checks passed!`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend && mypy app/services/reporting_service.py app/api/reports.py` — `Success: no issues found in 2 source files`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend && pytest -q tests/test_reports_inventory.py` — `4 passed in 3.81s`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting && git diff --check` — успешно, ошибок форматирования diff нет.
- `python3 scripts/ci/back_guard.py` — не применим: переделка не добавляет роут; сам скрипт в рабочей копии отсутствует.
- `python3 scripts/ci/check_migrations.py` — не применим: миграций нет; сам скрипт в рабочей копии отсутствует.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting && git add -- backend/tests/test_reports_inventory.py night/volna-9-recovery/cards/07-reporting/DEV.md && git diff --cached --check && git diff --cached --stat && git commit -m "test(reports): cover Moscow inventory boundary"` — не выполнено: Git не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-1-07-reporting1/index.lock`, ошибка `Operation not permitted`.

## Не реализовано

- Находки review по списку складов, декабрьскому пресету, отображению warning и `integrity_error`, а также независимому retry относятся к frontend и не входят в роль `backend-dev` атома 7.
- Находки по заполнению нулевых дней графика и свежести импорта относятся к сводке атома 6; в текущем атоме они не менялись.
- Секреты, ключи, токены, `.env` и кабинеты учётных данных не читались.

## Блокеры

- Изменения локально реализованы и проверены, но не сохранены отдельным коммитом: политика файловой системы не разрешает запись в общий Git-каталог зарегистрированного worktree. Чужое изменение `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/night/volna-9-recovery/JOURNAL.md` не изменялось и не добавлялось в индекс этой ролью.
