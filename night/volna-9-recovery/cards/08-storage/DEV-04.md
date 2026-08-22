# DEV · 08-storage · атом 4 · переделка по ревью

## Что реализовано

- `GET /products/{product_id}/dimensions/history` — ответ истории приведён к DTO живого экрана: `created_at`, `author_name`, `is_current`, источники `manual` / `wildberries` / `container`; авторы загружаются одним tenant-ограниченным запросом.
- `PATCH /products/{product_id}/dimensions` — API-тестами закреплено сохранение полного ручного обмера сотрудником с правом `inventory`, а также запрет неполных и нулевых значений без частичной записи.
- `POST /products/{product_id}/dimensions/container` — API-тестами закреплено сохранение объёма тары с основанием и отклонение нулевого объёма либо пустого основания без частичной записи.
- `POST /products/{product_id}/dimensions/restore-wb` — API-тестами закреплён запрет для сотрудника и успешный возврат последней WB-версии только администратором ФФ.

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/app/api/products.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/tests/test_products_api.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/night/volna-9-recovery/cards/08-storage/DEV.md`

## Миграции

- Нет.

## Тесты

- `test_inventory_staff_saves_both_measurements_and_reads_ui_history` проверяет оба способа обмера, хронологию, публичные названия источников, автора и единственную действующую версию.
- `test_invalid_measurements_and_foreign_tenant_do_not_write_history` проверяет неполные и нулевые значения, tenant-изоляцию и отсутствие частичной записи.
- `test_only_admin_can_restore_latest_wb_dimensions` проверяет право `inventory`, отказ сотруднику в возврате WB, отказ сотруднику без `inventory` в обмере и успешный возврат WB администратором.

## Гейты

- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend && ruff check app/api/products.py tests/test_products_api.py` — пройдено, `All checks passed!`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend && mypy app/api/products.py tests/test_products_api.py` — изменённые файлы очищены; общий граф импортов сообщает четыре ранее существовавшие ошибки вне атома: `app/services/wildberries_credentials_service.py:167`, `app/services/fbs_stock_sync_service.py:617`, `app/services/fbs_warehouse_binding_service.py:23,291`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend && mypy --follow-imports=silent app/api/products.py tests/test_products_api.py` — пройдено, `Success: no issues found in 2 source files`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend && pytest -q tests/test_products_api.py` — пройдено, `3 passed in 4.93s`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend && git diff --check` — пройдено, замечаний нет.
- `back_guard.py` и `check_migrations.py` не запускались: переделка не добавляет маршрут или миграцию.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage && git add backend/app/api/products.py backend/tests/test_products_api.py night/volna-9-recovery/cards/08-storage/DEV.md && git diff --cached --check && git commit -m "fix(storage): align dimension history API"` — не выполнено: Git не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-2-08-storage1/index.lock`, `Operation not permitted`.

## Не реализовано

- Находки ревью № 1–7 и № 9–10 относятся к другим атомам и прямо названным файлам API хранения, сервисов, миграций либо frontend; в атоме 4 они не изменялись.
- Старые внутренние поля истории `observed_at`, `author_user_id`, `applied` намеренно больше не публикуются: утверждённый живой экран использует `created_at`, `author_name`, `is_current`.
- Результат локально реализован, но не сохранён Git-коммитом и не опубликован: среда запрещает запись в общий каталог метаданных текущего worktree.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных, Wildberries и боевой production не читались и не изменялись.

## Блокеры

- Сохранение отдельным коммитом заблокировано правами среды на `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-2-08-storage1`; код, тесты и `DEV.md` находятся только в рабочем дереве.
