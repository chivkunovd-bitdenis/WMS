# DEV · 04-warehouse-switch · backend-dev

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/app/services/fbs_warehouse_binding_service.py` — активная WB→WMS-привязка теперь принимает только операционный склад.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/app/services/fbs_stock_availability_service.py` — остаток отсекает служебные склады на уровне запроса.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/app/services/fbs_supply_validator_service.py` — добавлен агрегированный stock preflight: суммарная проверка по операционным складам, рекомендация по покрытию и строки warning/blocking.

## Миграции

Нет: необходимые `Warehouse.is_operational` и существующая схема уже доступны.

## Гейты

- ruff: PASS для изменённых файлов; полный backend `ruff check .` BLOCKED существующими ошибками в unrelated-файлах (80 ошибок).
- mypy: BLOCKED существующими ошибками в unrelated-файлах; для изменённых сервисов новых ошибок кроме двух ранее существовавших `dict` в binding-файле не добавлено.
- pytest: целевые тесты `21 passed, 1 skipped, 1 failed`; fail — календарный тест с фиксированной датой заказа 2026-08-15 при текущей дате 2026-08-22. Полный прогон продолжен отдельно.
- back_guard.py: не запущен — `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/scripts/ci/back_guard.py` отсутствует в рабочей копии.
- check_migrations.py: не запущен — `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/scripts/ci/check_migrations.py` отсутствует в рабочей копии.

## Не реализовано

- UI-вывод warning/error и выбор склада не реализованы: это frontend-часть следующих атомарных кусков, не входящая в роль backend-dev.
- Новая отдельная API-ручка не добавлялась; preflight расширен в существующем ответе `POST /operations/fbs-supplies/preflight`.

## Блокеры

Технический: commit не создан — Git не может создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-1-04-warehouse-switch/index.lock` (`Operation not permitted`), так как служебный Git-каталог находится вне разрешённой области записи. Изменения остаются в рабочем diff и не могут быть объявлены готовыми до сохранения в commit.
