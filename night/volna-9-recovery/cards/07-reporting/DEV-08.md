# DEV · 07-reporting · атом 8

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend/app/services/reporting_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/night/volna-9-recovery/cards/07-reporting/DEV.md`

Добавлен текущий остаток в product-строки отчёта и в CSV, с теми же ограничениями tenant, операционного склада и выбранного склада. Существующий endpoint `/reports/inventory/export.csv` уже применял seller scope, warehouse scope, search, group_by, порядок и доменные ошибки пустого среза/периода свыше 366 дней; отдельный роут не добавлялся.

## Гейты

- `ruff check app/services/reporting_service.py app/api/reports.py tests/test_reports_csv_export.py` — PASS.
- `mypy app/services/reporting_service.py app/api/reports.py` — PASS.
- `pytest -q tests/test_reports_csv_export.py tests/test_reports_inventory.py` — PASS, 4 passed.
- `python3 scripts/ci/back_guard.py` — BLOCKED: файл отсутствует в этой рабочей копии (`scripts/ci/back_guard.py` не найден).
- `python3 scripts/ci/check_migrations.py` — BLOCKED: файл отсутствует в этой рабочей копии (`scripts/ci/check_migrations.py` не найден).
- Полный `ruff check .` — FAIL на существующих несвязанных нарушениях репозитория; затронутые файлы проходят.

## Не реализовано

- Новая миграция для этого атома не требуется.
- Замечание ревью о SQL миграции `20260822_0094_inventory_movement_reporting_dimensions.py` относится к фундаментальному атому 07-A и не изменялось в рамках разрешённых файлов атома 8.
- Сквозной API-тест с непустыми движениями и сравнением CSV с таблицей не добавлен: текущие доступные тесты покрывают endpoint и доменные ошибки, но фабрика данных для inventory-среза отсутствует в `test_reports_csv_export.py`; изменение ограничено слоем CSV-экспорта.

## Находки

- Секреты, ключи, токены, `.env` и кабинеты учётных данных не читались.
