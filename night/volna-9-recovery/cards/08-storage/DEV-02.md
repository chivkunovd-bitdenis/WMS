# DEV · 08-storage · backend-dev

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/app/api/products.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/app/services/catalog_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/app/services/wildberries_product_import_service.py`

Исправлена атомарная часть хранения версий габаритов: fingerprint учитывает источник и объём, WB-наблюдение больше не перезаписывает действующий ручной обмер или объём тары, ручной автор сохраняется при активации версии, сотрудники с правом `inventory` могут вносить обмер, а история товара проверяет принадлежность селлеру.

Миграции: нет; миграция `20260822_0095_product_dimension_events.py` уже присутствует и не изменялась.

## Гейты

- ruff: целевые файлы прошли; полный `ruff check .` заблокирован 23 существующими ошибками в несвязанных файлах.
- mypy: полный и целевой запуск заблокирован 5 существующими ошибками в несвязанных местах; новых ошибок в изменённых строках не выявлено.
- pytest: `tests/test_wb_import_dimensions.py tests/test_catalog.py` — 9 passed.
- back_guard.py: не запущен — `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/scripts/ci/back_guard.py` отсутствует в этой рабочей копии.
- check_migrations.py: не запущен — `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/scripts/ci/check_migrations.py` отсутствует в этой рабочей копии.

## Не реализовано

- Замечания ревью по расчёту хранения, биллингу, тарифам, печати и фронтенду не относятся к этому атомарному backend-слою и не изменялись.
- `external_updated_at` не заполняется: текущий WB-клиент не передаёт дату обновления карточки; поле миграции сохранено для будущего значения.

Блокеры: Git-коммит не создан: Git пытается создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-2-08-storage1/index.lock`, путь находится вне разрешённой рабочей копии и недоступен для записи. Изменения локальны и требуют сохранения/коммита владельцем или расширения прав.
