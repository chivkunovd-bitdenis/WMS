# DEV · 08-storage · атом 3 · переделка по ревью

## Что реализовано

- Сервис расчёта хранения исключает WB-наблюдения, записанные поверх действующего ручного обмера или объёма тары, из временной шкалы применённых габаритов.
- Явный возврат к WB остаётся новой действующей версией и меняет объём только с момента возврата; завершившийся ранее период сохраняет ручной объём.
- Существующая реализация `catalog_service.py` проверена на находку ревью № 5: повторный осознанный ручной обмер создаёт новое неизменяемое событие и не переписывает автора старого события.
- Новые эндпоинты не добавлялись.

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/app/services/storage_measurement_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/tests/test_storage_measurement_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/night/volna-9-recovery/cards/08-storage/DEV.md`

## Миграции

- Нет.

## Тесты

- Добавлен сценарий: новое WB-наблюдение после ручного обмера не меняет объём в расчёте хранения.
- Добавлен сценарий: явный возврат к последней полной WB-версии меняет открытую временную шкалу с момента возврата и не меняет завершившийся ранее период.
- Повторно проверены сценарии полного ручного обмера, объёма тары без основания и с основанием, одинакового повторного WB-импорта, WB-обновления после ручного обмера, возврата к WB и повторного ручного обмера тем же значением с сохранением старых даты и автора.

## Гейты

- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend && ruff check app/services/catalog_service.py app/services/wildberries_product_import_service.py app/services/storage_measurement_service.py tests/test_product_dimension_history.py tests/test_storage_measurement_service.py` — пройдено, `All checks passed!`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend && mypy app/services/storage_measurement_service.py tests/test_storage_measurement_service.py` — пройдено, `Success: no issues found in 2 source files`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend && mypy app/services/catalog_service.py app/services/wildberries_product_import_service.py app/services/storage_measurement_service.py tests/test_product_dimension_history.py tests/test_storage_measurement_service.py` — затронутые файлы очищены; общий граф импортов сообщает четыре ранее существовавшие ошибки вне атома: `app/services/wildberries_credentials_service.py:167`, `app/services/fbs_stock_sync_service.py:617`, `app/services/fbs_warehouse_binding_service.py:23,291`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend && pytest -q tests/test_product_dimension_history.py tests/test_wb_import_dimensions.py tests/test_storage_measurement_service.py` — пройдено, `15 passed in 6.20s`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend && git diff --check` — пройдено, замечаний нет.
- `back_guard.py` и `check_migrations.py` не запускались: атом не добавляет маршрут или миграцию.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage && git add backend/app/services/storage_measurement_service.py backend/tests/test_storage_measurement_service.py night/volna-9-recovery/cards/08-storage/DEV.md && git diff --cached --check && git commit -m "fix(storage): preserve manual dimensions in calculations"` — не выполнено: Git не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-2-08-storage1/index.lock`, `Operation not permitted`.

## Не реализовано

- Нет пунктов атома 3, которые не легли буквально. Находки ревью о list API, биллинге, складских движениях, тарифах, текущем месяце, DTO фронтенда, правах маршрута и Playwright относятся к другим атомам и их файлам; в этой переделке они не затрагивались.
- Результат локально реализован, но не сохранён Git-коммитом и не опубликован: среда запрещает запись в общий каталог метаданных текущего worktree.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных и боевой production не читались и не изменялись.

## Блокеры

- Сохранение отдельным коммитом заблокировано правами среды на `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-2-08-storage1`; код и `DEV.md` находятся только в рабочем дереве.
