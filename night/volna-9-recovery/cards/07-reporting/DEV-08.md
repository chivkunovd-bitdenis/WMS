## Изменённые файлы

- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend/app/services/reporting_service.py — добавлен полный CSV-срез с теми же фильтрами, группировкой, сортировкой и seller scope, что у таблицы.
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend/app/api/reports.py — добавлен потоковый `GET /reports/inventory/export.csv` с CSV MIME type и доменными ошибками.
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend/tests/test_reports_csv_export.py — проверки пустого среза и периода длиннее 366 дней.

## Гейты

- ruff: GREEN для изменённых backend-файлов; полный `ruff check .` BLOCKED существующими 82 нарушениями в несвязанных файлах.
- mypy: GREEN для `app/api/reports.py` и `app/services/reporting_service.py`.
- pytest: GREEN — целевые CSV и inventory тесты, 4 passed.
- back_guard.py: BLOCKED — `scripts/ci/back_guard.py` отсутствует в этой рабочей копии.
- check_migrations.py: BLOCKED — `scripts/ci/check_migrations.py` отсутствует в этой рабочей копии.

## Не реализовано

- Поля текущего остатка в строках CSV не добавлялись: экспорт повторяет фактические агрегированные колонки существующего `/reports/inventory`, согласно зависимости от фичи 7.
- Полный тест с заполненными движениями и сравнением CSV с таблицей не добавлен: доступные API-фабрики карточки создают только пользователя, без данных отчёта; добавлены проверки доменных отказов.
- Секреты, ключи, токены, `.env` и кабинеты учётных данных не читались.
