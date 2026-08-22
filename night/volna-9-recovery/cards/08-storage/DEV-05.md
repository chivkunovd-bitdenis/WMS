# Backend implementation report — 08-storage

## Изменённые файлы

- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/app/models/storage_measurement.py
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/app/models/storage_statement.py
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/app/models/__init__.py
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/alembic/versions/20260822_0096_storage_measurements_and_statements.py

## Что реализовано

`StorageMeasurement` хранит tenant, seller, операционный склад, SKU, версию габаритов, начало и конец диапазона движений, точное количество-дни, литро-дни и статус без денежных полей.

`StorageStatement` группирует tenant, seller, склад и календарный период; уникальное ограничение запрещает второй документ для того же tenant/селлера/склада/месяца.

## Миграции

`20260822_0096` — добавляет таблицы `storage_measurements` и `storage_statements`, внешние ключи на существующие сущности и индексы; тарифы, начисления и денежные таблицы не добавляет.

## Тесты

Новых тестов не добавлял: в этой части нет эндпоинтов и сервисной логики. Импорт ORM-моделей проверен отдельной командой; миграция содержит уникальность месячного документа.

## Гейты

- ruff — FAIL на полном проекте из-за 98 существующих ошибок; новые файлы после форматирования проходят `ruff check`.
- mypy — FAIL на 4 существующих ошибках в `wildberries_credentials_service.py`, `fbs_stock_sync_service.py` и `fbs_warehouse_binding_service.py`.
- pytest — прерван после 133.49 с из-за длительности полного набора: 192 passed, 3 skipped, 5 warnings; до остановки падений не было.
- back_guard.py — файл отсутствует в этой рабочей копии (`scripts/ci/back_guard.py` не найден).
- check_migrations.py — файл отсутствует в этой рабочей копии (`scripts/ci/check_migrations.py` не найден).

## Не реализовано

- Строгая проверка, что склад операционный, и проверка `InventoryMovement.warehouse_id` невозможны буквально в этой карточке: фундамент 07-A ещё не добавлен в рабочую копию и соответствующего поля в текущей модели нет. Миграция сохраняет диапазон через `movement_start_id`/`movement_end_id` и прямую ссылку на `warehouse_id`, не создавая дублирующий складской контракт.

## Блокеры

Коммит невозможен в этой sandbox-копии: Git не может создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-2-08-storage1/index.lock` (Operation not permitted). Изменения остаются в рабочем дереве и не имеют проверенного commit SHA.
