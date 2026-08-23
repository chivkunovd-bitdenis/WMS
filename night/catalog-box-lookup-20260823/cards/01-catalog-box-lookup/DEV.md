# DEV · Read-only API коробов и грузомест для каталога

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/backend/app/services/inbound_package_catalog_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/backend/app/api/inbound_package_catalog.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/backend/app/main.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/backend/tests/test_inbound_package_catalog.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/night/catalog-box-lookup-20260823/cards/01-catalog-box-lookup/DEV.md`

Реализованы `GET /operations/inbound-packages` и
`GET /operations/inbound-packages/lookup?barcode=...`. Оба используют
`require_catalog_cells_read_access`; сервис читает данные текущего тенанта,
считает только `max(quantity - posted_qty, 0)` и не вызывает изменяющее
`open_box_by_barcode`.

## Миграции

Нет: переиспользованы существующие таблицы приёмки только для чтения.

## Тесты

- `backend/tests/test_inbound_package_catalog.py` — состав обычного списка,
  положительный остаток, новый пустой короб, исключение полностью разложенного
  короба, незавершённое грузоместо и стабильный порядок.
- Точный поиск завершённого короба и грузоместа, одинаковый `404` для
  неизвестного и чужого штрихкода, тенантная граница и отсутствие побочных
  изменений `intake_opened_at`, `intake_closed_at`, количеств и статуса.
- Доступ администратора, сотрудников с `cells`/`inventory` и отказ сотруднику
  только с правом приёмки.

## Гейты

- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/backend && ruff check app/services/inbound_package_catalog_service.py app/api/inbound_package_catalog.py app/main.py tests/test_inbound_package_catalog.py` — пройдено: `All checks passed!`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/backend && mypy app/services/inbound_package_catalog_service.py app/api/inbound_package_catalog.py app/main.py` — в изменённых модулях ошибок нет; команда завершается с 6 существующими ошибками в импортируемых, не затронутых сервисах: `inventory_movement_report_service.py`, `wildberries_credentials_service.py`, `fbs_stock_sync_service.py`, `fbs_warehouse_binding_service.py`, `wildberries_product_import_service.py`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/backend && pytest -q tests/test_inbound_package_catalog.py` — пройдено: `2 passed`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup && python3 scripts/ci/back_guard.py` — не выполнен: в рабочей копии отсутствует `scripts/ci/back_guard.py`; поиск по репозиторию также не нашёл этот файл.
- `check_migrations.py` не применим: миграций нет; файла скрипта в этой рабочей копии также нет.

## Находки

Секреты, ключи, токены, `.env` и кабинеты учётных данных не открывались. Боевой сервер не использовался.

## Не реализовано

Нет. Реализован только атом 1 из `FEATURES.md`; UI и e2e-атомы не затрагивались.
