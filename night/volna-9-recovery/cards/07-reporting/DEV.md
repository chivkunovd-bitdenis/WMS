## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend/app/services/reporting_service.py` — сводка и inventory-отчёт фильтруют движения по зафиксированному `InventoryMovement.seller_id`; сводка принимает склад и поиск и применяет их к показателям, сравнению, сериям и текущему остатку.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend/app/api/reports.py` — `GET /reports/overview` принимает `seller_id`, `warehouse_id`, `search`; seller scope принудительно сохраняется.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/night/volna-9-recovery/cards/07-reporting/DEV.md` — этот отчёт.

## Гейты

- `ruff check backend/app/services/reporting_service.py backend/app/api/reports.py` — зелёный.
- `mypy backend/app/services/reporting_service.py backend/app/api/reports.py` — зелёный.
- `pytest backend/tests/test_reports_overview.py backend/tests/test_reports_inventory.py` — зелёный, 4 passed.
- `ruff check .` из `backend/` — красный на 82 ранее существующих нарушениях вне изменённых файлов.
- `mypy .` и полный `pytest` — не запускались из-за короткого замыкания команды после красного полного ruff.
- `python3 scripts/ci/back_guard.py` — не запущен: файл отсутствует в этой рабочей копии.
- `python3 scripts/ci/check_migrations.py` — не запущен: файл отсутствует в этой рабочей копии.

## Не реализовано

- Фильтрация по `Warehouse.is_operational` и предупреждение legacy не добавлены: в текущей рабочей копии у модели `Warehouse` и схемы нет поля `is_operational`; его добавление относится к зависимому 04-D/07-A фундаменту и расширило бы атом.
- Исправление миграции 0094 отдельно не потребовалось: текущий файл уже использует коррелированные подзапросы, не содержащие запрещённой ссылки на target table в `FROM`/`JOIN`.
- Frontend-находки ревью не реализованы: роль ограничена backend.

## Находки

- В рабочем дереве уже были несвязанные изменения: изменён `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/night/volna-9-recovery/JOURNAL.md` и удалён исходный `DEV.md`; они не редактировались в рамках backend-атома.
