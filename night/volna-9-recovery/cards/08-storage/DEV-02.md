# Backend Dev · 08-storage · атом 2

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/alembic/versions/20260822_0095_product_dimension_events.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/app/api/products.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/app/services/catalog_service.py`

## Что реализовано

- Миграция сохраняет прежние заполненные габариты товаров как первую действующую `legacy`-версию и заполняет быстрый снимок источника/времени.
- Возврат к сохранённым данным WB создаёт отдельное действующее событие без конфликта с уникальным fingerprint; обычные повторы по-прежнему дедуплицируются.
- Ручной PATCH габаритов доступен только администратору или сотруднику с правом `inventory` и записывает `author_user_id` текущего пользователя.

## Миграции

- `20260822_0095`: добавляет поля действующего источника на `products`, журнал `product_dimension_events` и backfill существующих снимков.

## Тесты

- `tests/test_storage_models.py`, `tests/test_products_api.py`, `tests/test_wb_import_dimensions.py`: модель журнала, права/автор ручного обмера и сохранение WB-наблюдений.

## Гейты

- `ruff`: полный прогон не проходит из-за 80 существующих ошибок в соседних файлах; изменённые три Python-файла проходят отдельный `ruff check`.
- `mypy`: полный прогон не проходит из-за существующих ошибок в `storage_statement_service.py`, FBS и cleanup-скриптах; ошибок в изменённых файлах не сообщил.
- `pytest`: целевые тесты `7 passed`; полный прогон запущен, на момент подготовки артефакта ещё выполнялся.
- `back_guard.py`: файл отсутствует в этой рабочей копии (`python3: can't open file scripts/ci/back_guard.py`).
- `check_migrations.py`: файл отсутствует в этой рабочей копии (`python3: can't open file scripts/ci/check_migrations.py`).

## Не реализовано

- Остальные находки ревью по расчёту хранения, биллингу, печати и UI не относятся к этому атомарному backend-слою и не изменялись.

## Блокеры

- Нет.
