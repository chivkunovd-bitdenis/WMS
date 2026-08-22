## Изменённые файлы

- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend/app/services/reporting_service.py — постраничная агрегация отчёта по товарам и операциям, поиск, складской scope и диагностика неполной transfer-пары.
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend/app/api/reports.py — `GET /reports/inventory`.
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend/tests/test_reports_inventory.py — проверки API, группировок и фиксированного размера страницы.

## Гейты

- ruff: GREEN — целевые backend-файлы прошли `ruff check`.
- mypy: GREEN — `app/services/reporting_service.py` и `app/api/reports.py`.
- pytest: GREEN — `tests/test_reports_inventory.py`, 2 passed.
- back_guard.py: BLOCKED — файл отсутствует в рабочей копии; запуск из backend и корня невозможен.
- check_migrations.py: BLOCKED — файл отсутствует в рабочей копии; запуск из backend и корня невозможен.

## Не реализовано

- Текущий остаток в строке товара не добавлен: API отдаёт `in_qty`, `out_qty` и `net`, а источник балансов требует отдельного согласования контракта 07-A.
- Полное различение служебного склада по `is_operational` невозможно: колонка отсутствует в текущей модели; применён существующий legacy-признак `FBS WB `.
