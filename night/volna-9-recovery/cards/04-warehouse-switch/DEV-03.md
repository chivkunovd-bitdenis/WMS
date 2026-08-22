# DEV · 04-warehouse-switch · атом 3

## Что реализовано

- `GET /operations/fbs-supplies/worklist` — существующий эндпоинт принимает необязательный `warehouse_id` и возвращает только поставки выбранного физического WMS-склада.
- `list_supply_worklist` — проверяет, что склад принадлежит tenant и является операционным, затем фильтрует по неизменяемому `FbsSupply.warehouse_id`; переключение фильтра не переписывает исторический документ.
- Существующие `POST /operations/fbs-supplies/from-orders` и `PATCH /operations/fbs-supplies/{supply_id}/warehouse` подтверждены целевыми тестами: новая поставка принимает рекомендованный или явно выбранный операционный склад, незапущенная меняет его, а после подбора получает `409` с сообщением «Склад закреплён: подбор уже начат».

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/app/api/fbs_supplies.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/app/services/fbs_supply_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/tests/test_fbs_supply_from_orders.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/night/volna-9-recovery/cards/04-warehouse-switch/DEV.md`

## Миграции

Нет.

## Тесты

- Добавлен `test_supply_worklist_filters_by_operational_warehouse`: создаёт две поставки на разных операционных складах, переключает складской фильтр и проверяет, что каждый список содержит только свой документ, а сохранённый `warehouse_id` исторической поставки не меняется.
- Повторно проверены существующие сценарии создания на явно выбранном и рекомендованном складе, смены склада до первого действия, запрета после подбора и группировки списка поставок.

## Гейты

- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend && ruff check app/api/fbs_supplies.py app/services/fbs_supply_service.py tests/test_fbs_supply_from_orders.py` — пройдено: `All checks passed!`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend && mypy app/api/fbs_supplies.py app/services/fbs_supply_service.py tests/test_fbs_supply_from_orders.py` — не пройдено: 4 ранее существовавшие ошибки в импортируемых `wildberries_credentials_service.py`, `fbs_stock_sync_service.py` и `fbs_warehouse_binding_service.py`; в строках текущего diff ошибок нет.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend && pytest -q tests/test_fbs_supply_from_orders.py -k 'warehouse_switch_is_locked_after_pick or creation_uses_selected_operational_warehouse or creation_without_selection_uses_recommended_warehouse or supply_worklist_groups_active_orders_by_supply or supply_worklist_filters_by_operational_warehouse'` — пройдено: `5 passed, 16 deselected in 9.46s`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch && git diff --check` — пройдено, ошибок форматирования diff нет.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch && git add backend/app/api/fbs_supplies.py backend/app/services/fbs_supply_service.py backend/tests/test_fbs_supply_from_orders.py night/volna-9-recovery/cards/04-warehouse-switch/DEV.md && git commit -m 'night(04-warehouse-switch): atom 3/13'` — не выполнено: Git не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-1-04-warehouse-switch/index.lock`, ошибка `Operation not permitted`.
- `python3 scripts/ci/back_guard.py` — не применим: новый маршрут не добавлялся, расширен существующий `GET /operations/fbs-supplies/worklist`, покрытый новым API-тестом.
- `python3 scripts/ci/check_migrations.py` — не применим: миграций в атоме нет.

## Не реализовано

- Находка ревью №1 относится к атомарной фиче 2 и файлу `backend/app/services/fbs_supply_validator_service.py`; в атоме 3 этот сервис не изменялся.
- Находки ревью №2–9 и №12 относятся к frontend или соседним продуктовым атомам; роль `backend-dev` их не меняла.
- Находка ревью №10 относится к внешнему контракту 07-A и модели движений; она не входит в файлы и поведение атома 3.
- Реестр блокировок из находки №11 не менялся: обязательная серверная блокировка `supply_warehouse_locked` уже реализована и проверена здесь, а расширение общего реестра выходит за границы трёх файлов атома.

## Блокеры

- Целевые ruff и pytest пройдены. Единственное ограничение гейтов — ранее существовавшие mypy-ошибки в импортируемых модулях вне текущего diff.
- Результат локально реализован, но не сохранён Git-коммитом: sandbox не разрешает запись в общий служебный каталог `.git`, находящийся вне разрешённого корня worktree. Нужен запуск `git add` и `git commit` процессом с правом записи в основной `.git`.
