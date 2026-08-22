## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend/app/models/warehouse.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend/app/services/reporting_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend/alembic/versions/20260822_0095_warehouse_operational_flag.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend/tests/test_reports_csv_export.py`

## Гейты

- `ruff check` по изменённым backend-файлам — пройден после форматирования.
- `mypy` по изменённым model/service/api — пройден.
- `pytest -q backend/tests/test_reports_csv_export.py` — пройдено, 2 passed.
- `python3 scripts/ci/back_guard.py` — не запущен: скрипт отсутствует в этой рабочей копии.
- `python3 scripts/ci/check_migrations.py` — не запущен: скрипт отсутствует в этой рабочей копии.
- Полный `ruff check .` — не пройден из-за 83 ранее существующих нарушений вне изменённых файлов.

## Не реализовано

- API-эндпоинт CSV уже был добавлен предыдущим атомом; в этом проходе исправлены общие backend-фильтры, от которых зависит его честное совпадение с таблицей.
- Дополнительная seeded-проверка строк CSV с непустым срезом не добавлялась: текущие API-тесты создают только организацию без складских движений.
- Обнаруженные в окружении отсутствующие guard-скрипты не восстанавливались, чтобы не расширять атом.
- Коммит невозможен в текущем sandbox: Git не может создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-1-07-reporting1/index.lock` (`Operation not permitted`). Изменения остаются в этой рабочей копии и требуют коммита владельцем окружения.

## Находки

- Секреты, токены, `.env` и кабинеты учётных данных не читались.
