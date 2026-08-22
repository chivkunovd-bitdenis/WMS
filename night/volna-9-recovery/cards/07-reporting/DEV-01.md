# Backend Dev · 07-reporting · атом 1

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend/alembic/versions/20260822_0094_inventory_movement_reporting_dimensions.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend/tests/test_inventory_movement_reporting_dimensions.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/night/volna-9-recovery/cards/07-reporting/DEV.md`

Исправлен backfill измерений движения: PostgreSQL-совместимые коррелированные подзапросы вместо недопустимого `JOIN` с alias целевой таблицы. Перед переводом `warehouse_id` в `NOT NULL` миграция теперь явно останавливается при неразрешимой исторической привязке, не подставляя догадку. Тест проверяет эту форму SQL.

## Миграции

- `20260822_0094` — изменена существующая добавляющая миграция: backfill `seller_id`, `warehouse_id`, `reporting_dimensions_legacy`; проверка полноты `warehouse_id`; составные индексы без изменений.

## Гейты

- `ruff check .` — FAIL: 82 pre-existing ошибок в несвязанных файлах backend; ошибок в изменённых файлах отдельно не выявлено.
- `mypy .` — FAIL: 20 pre-existing ошибок в несвязанных сервисах и cleanup-скрипте; `mypy app/models/inventory_movement.py` — PASS.
- `pytest` — целевой `tests/test_inventory_movement_reporting_dimensions.py`: PASS, 2 passed.
- `python3 scripts/ci/back_guard.py` — BLOCKED: файл отсутствует в рабочей копии.
- `python3 scripts/ci/check_migrations.py` — BLOCKED: файл отсутствует в рабочей копии.
- `git diff --check` — PASS.

## Не реализовано

- Остальные находки `REVIEW.md` по reporting API, CSV и frontend не относятся к этому атомарному backend-изменению и не трогались.
- Полное исполнение миграции на PostgreSQL не проведено: в окружении нет доступной тестовой базы; SQL теперь не использует запрещённую форму `UPDATE ... FROM ... JOIN`.

## Блокеры

- Нет блокеров для внесённого исправления; общие гейты ограничены существующими ошибками репозитория и отсутствующими скриптами.
