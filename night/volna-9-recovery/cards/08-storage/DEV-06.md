# DEV · 08-storage · backend-dev

## Изменённые файлы

- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/app/services/storage_measurement_service.py
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/app/services/background_job_service.py
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/app/api/storage.py
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/night/volna-9-recovery/cards/08-storage/DEV.md

## Что реализовано

- Расчёт месячного черновика использует календарные границы и доли суток в часовом поясе МСК.
- Повторный rebuild не добавляет строки к закрытому statement; открытые строки пересчитываются идемпотентно.
- Для периода без движений создаются нулевые draft statements по доступным seller/warehouse scope.
- Добавлен seller scope для фонового задания и право `inventory` для запуска rebuild через API.
- При наличии `InventoryMovement.warehouse_id` расчёт использует зафиксированный склад движения; fallback на storage location оставлен для старых данных до 07-A.

## Миграции

Нет. Схема не менялась.

## Тесты

- Целевые storage-тесты: 5 passed.
- Полный `pytest` запущен; на момент подготовки артефакта процесс ещё выполнялся.

## Гейты

- `ruff`: целевые изменённые файлы — passed; полный `ruff check .` — failed на существующих несвязанных ошибках в других backend-файлах.
- `mypy`: изменённые сервис/API проверены; полный/связанный запуск выявил существующие ошибки в `wildberries_credentials_service.py` и `fbs_stock_sync_service.py`, не относящиеся к этому атому.
- `pytest`: целевые тесты — passed; полный прогон запущен, итог ожидается.
- `back_guard.py`: не запущен — файл `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/scripts/ci/back_guard.py` отсутствует в этой рабочей копии.
- `check_migrations.py`: не запущен по той же причине; миграций нет.

## Не реализовано

- Поле `InventoryMovement.warehouse_id` и `Warehouse.is_operational` отсутствуют в текущей рабочей копии: сервис использует immutable поле, если фундамент 07-A уже присутствует, иначе совместимый fallback через location. Добавление соседней миграции 07-A в этот атом не выполнялось.
- Финансовая фиксация/ledger, печатный A4-контракт, WB-защита габаритов и UI находятся в других атомах и не изменялись.

## Блокеры

Изменения локальны и не сохранены commit: Git не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-2-08-storage1/index.lock` (`Operation not permitted`). Обязательные корневые CI-скрипты также отсутствуют в рабочей копии.
