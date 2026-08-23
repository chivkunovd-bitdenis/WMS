# DEV · 01-catalog-box-lookup · атом 2

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/backend/app/services/inbound_package_catalog_service.py` — read-модель короба получила явный признак `fully_distributed`: он истинен только для короба с хотя бы одной строкой, у которого весь объём разложен (`quantity == posted_qty` для каждой строки), независимо от статуса приёмки.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/backend/app/api/inbound_package_catalog.py` — оба существующих GET-ответа каталога передают `fully_distributed`; для грузоместа признак всегда `false`.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/backend/tests/test_inbound_package_catalog.py` — тест закрепляет адресный поиск полностью разложенного короба в приёмке `sorting`, нулевой остаток, пустые текущие строки и исключение объекта из обычного списка.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/night/catalog-box-lookup-20260823/cards/01-catalog-box-lookup/DEV.md` — отчёт роли `backend-dev` по атому 2.

## Миграции

Нет: изменена только read-модель существующих API, схема БД не менялась.

## Тесты

- `backend/tests/test_inbound_package_catalog.py` — `GET /operations/inbound-packages/lookup` для `INB-CURRENT-DISTRIBUTED` в приёмке `sorting` возвращает `fully_distributed: true`, `remaining_qty: 0` и пустой состав; обычный `GET /operations/inbound-packages` этот короб не включает.

## Гейты

- Зелёный: `git diff --check` — ошибок пробелов нет.
- Зелёный: `ruff check app/services/inbound_package_catalog_service.py app/api/inbound_package_catalog.py ../backend/tests/test_inbound_package_catalog.py` (из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/backend`) — `All checks passed!`.
- Зелёный: `mypy app/services/inbound_package_catalog_service.py app/api/inbound_package_catalog.py` (из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/backend`) — `Success: no issues found in 2 source files`.
- Зелёный: `pytest -q tests/test_inbound_package_catalog.py` (из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/backend`) — `2 passed in 4.05s`.
- `python3 scripts/ci/back_guard.py` и `python3 scripts/ci/check_migrations.py` не запускались: атом не добавляет маршрут и не добавляет миграцию.
- Не сохранено в Git: `git add backend/app/services/inbound_package_catalog_service.py backend/app/api/inbound_package_catalog.py backend/tests/test_inbound_package_catalog.py night/catalog-box-lookup-20260823/cards/01-catalog-box-lookup/DEV.md` не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-1-01-catalog-box-lookup/index.lock` (`Operation not permitted`), поэтому отдельный commit SHA получить в этом окружении нельзя.

## Не реализовано

- Находки ревью 1 и 3–8 не относятся к backend-слою этого атома или принадлежат следующим отдельным фичам из `FEATURES.md`; они намеренно не менялись.

## Находки

Нет находок о данных, секретах или персональных данных. Секреты, ключи, токены, `.env` и кабинеты учётных данных не открывались.
