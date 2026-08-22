# DEV · 08-storage · атом 5

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/app/models/storage_measurement.py` — добавлена уникальность измерения по tenant, селлеру, операционному складу, SKU и месяцу; это защищает повторный rebuild от дублей.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/alembic/versions/20260822_0096_storage_measurements_and_statements.py` — миграция создаёт тот же уникальный ключ; существующие ограничения отформатированы по лимиту ruff.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/tests/test_storage_models.py` — проверяет состав нового ключа и отсутствие изменяемой ссылки на ячейку вместо диапазона зафиксированных движений.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/night/volna-9-recovery/cards/08-storage/DEV.md` — отчёт backend-dev по атому.

## Миграции

- `20260822_0096_storage_measurements_and_statements` — добавляет `uq_storage_measurements_tenant_seller_warehouse_product_period`; отдельная таблица денег, локальный тариф или счёт не добавлялись.

## Тесты

- `test_measurement_is_unique_for_tenant_seller_warehouse_sku_and_month` — состав ключа идемпотентности monthly measurement.
- `test_measurement_keeps_immutable_movement_boundary_references` — измерение не содержит `storage_location_id` и хранит только FK на границы `InventoryMovement`.

## Гейты

- `ruff check backend/app/models/storage_measurement.py backend/app/models/storage_statement.py backend/tests/test_storage_models.py backend/alembic/versions/20260822_0096_storage_measurements_and_statements.py` — `All checks passed!`
- `cd backend && mypy -m app.models.storage_measurement -m app.models.storage_statement` — `Success: no issues found in 2 source files`.
- `cd backend && pytest -q tests/test_storage_models.py` — `5 passed`.
- `git diff --check` — пройден без вывода.
- `python3 scripts/ci/check_migrations.py` — не запущен: файла `scripts/ci/check_migrations.py` в этой рабочей копии нет.
- Эквивалентная проверка `cd backend && alembic heads` — обнаружила отсутствующую внешнюю ревизию `20260821_0094`, на которую ссылается уже существующая `20260822_0095`; изменения атома 5 эту внешнюю цепочку не меняют.
- `python3 scripts/ci/back_guard.py` неприменим: новых роутов в атоме нет.
- `git add … && git commit -m 'night(08-storage): enforce measurement idempotency'` — не выполнен: sandbox запретил создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-2-08-storage1/index.lock`. Изменения остаются в рабочем дереве и требуют коммита из среды с доступом к Git metadata.

## Не реализовано

- Из вердикта ревью №3 не менялся контракт `InventoryMovement.seller_id/warehouse_id`, backfill и writers: это единоличная зона внешнего фундамента 07-A по `ARCH-CROSS.md`, не слой атома 5.
- Денежная фиксация statement, выбор тарифа, печатный DTO и API из находок №2 и №5–9 не менялись: этот атом создаёт только неизменяемые модели и миграцию без финансовых таблиц или новых роутов.
- Нахождение внешней отсутствующей миграции `20260821_0094` записано выше как факт проверки; секреты, ключи, токены, `.env` и кабинеты учётных данных не читались.
