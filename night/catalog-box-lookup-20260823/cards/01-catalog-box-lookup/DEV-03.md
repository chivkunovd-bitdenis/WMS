# Backend dev · 01-catalog-box-lookup · атом 3

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/backend/app/services/inbound_package_catalog_service.py` — обычный список отбирает короба на уровне SQL: короб с положительным остатком либо пустой короб незавершённой приёмки; грузоместа завершённых приёмок исключаются до materialization (материализации результатов запроса).
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/backend/tests/test_inbound_package_catalog.py` — добавлена проверка HTTP-состава и SQL-предикатов, включая отсутствие идентификаторов полностью разложенных и завершённых коробов в запросе строк короба.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/night/catalog-box-lookup-20260823/cards/01-catalog-box-lookup/DEV.md` — отчёт этого атома.

## Гейты

- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/backend && ruff check app/services/inbound_package_catalog_service.py tests/test_inbound_package_catalog.py` — `All checks passed!`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/backend && mypy app/services/inbound_package_catalog_service.py` — `Success: no issues found in 1 source file`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/backend && pytest -q tests/test_inbound_package_catalog.py` — `3 passed`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup && git diff --check` — успешно.
- `python3 scripts/ci/back_guard.py` и `python3 scripts/ci/check_migrations.py` не запускались: атом не добавляет маршрут или миграцию.
- `git add … && git commit -m "fix: limit inbound package catalog queries"` — не выполнен: Git не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-1-01-catalog-box-lookup/index.lock` (`Operation not permitted`). Изменения остаются локальными и незафиксированными.

## Не реализовано

Нет: выполнен только атом 3 из `FEATURES.md`. Соседние находки ревью, относящиеся к frontend и e2e, намеренно не затрагивались.
