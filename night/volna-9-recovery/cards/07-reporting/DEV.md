# Backend development · 07-reporting · атом 1

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend/alembic/versions/20260822_0094_inventory_movement_reporting_dimensions.py` — backfill сохраняет доступные текущие измерения, но помечает каждую исторически реконструированную строку как `reporting_dimensions_legacy`, чтобы текущая связь не была выдана за доказанный факт прошлого.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend/tests/test_inventory_movement_reporting_dimensions.py` — зафиксирован консервативный контракт legacy-backfill и индексов.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/night/volna-9-recovery/cards/07-reporting/DEV.md` — отчёт атома.

## Гейты

- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend && ruff check app/models/inventory_movement.py alembic/versions/20260822_0094_inventory_movement_reporting_dimensions.py tests/test_inventory_movement_reporting_dimensions.py` — `All checks passed!`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend && mypy app/models/inventory_movement.py` — `Success: no issues found in 1 source file`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend && pytest -q tests/test_inventory_movement_reporting_dimensions.py` — `2 passed in 0.02s`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting && python3 scripts/ci/back_guard.py` — не применён: файла `scripts/ci/back_guard.py` в этой рабочей копии нет.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting && python3 scripts/ci/check_migrations.py` — не запускался, потому что названный скрипт также отсутствует в этой рабочей копии.
- `git diff --check` — без ошибок.

## Не реализовано

- Пункты следующих атомов из `FEATURES.md` не затрагивались.
- Фактический PostgreSQL round-trip миграции не запускался: в репозитории нет требуемых CI-скриптов, а отдельный тестовый URL базы не предоставлен. Целевой тест фиксирует SQL-контракт миграции.

## Находки

- Секреты, ключи, токены, `.env` и кабинеты учётных данных не читались.
