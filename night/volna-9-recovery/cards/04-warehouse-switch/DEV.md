# DEV · 04-warehouse-switch · backend-dev

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/app/services/fbs_picking_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/app/services/inventory_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/app/models/inventory_movement.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/alembic/versions/20260822_0095_inventory_movement_dimensions.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/tests/test_fbs_picking.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/night/volna-9-recovery/cards/04-warehouse-switch/DEV.md`

## Что реализовано

- `scan_pick_product` повторно проверяет ключ идемпотентности после блокировки поставки; кросс-складской FBS-pick и его undo явно разрешают только свой специализированный путь переноса.
- `transfer_on_hand_between_locations` снова запрещает перемещение между разными складами по умолчанию; товар без `seller_id` можно принять и записать в журнал, без постановки задачи публикации WB.

## Миграции

- `20260822_0095_inventory_movement_dimensions`: `seller_id` в движениях остаётся nullable, чтобы не ломать исторические и обычные FF-товары без селлера; `warehouse_id` остаётся обязательным.

## Тесты

- `test_generic_inventory_transfer_rejects_another_warehouse`: общий writer отклоняет межскладской перенос.
- `test_fbs_picking.py`: 9 passed, включая идемпотентность и undo полной пары.
- `test_fbs_packaging_integration.py`: 15 passed, включая запрет списания из чужой сортировки и отсутствие обхода.

## Гейты

- ruff: целевые изменённые файлы — `All checks passed`; полный `ruff check .` не прошёл из-за 80 существующих ошибок вне этого атома.
- mypy: не прошёл из-за 4 существующих ошибок в `wildberries_credentials_service.py`, `fbs_stock_sync_service.py` и `fbs_warehouse_binding_service.py`; изменённые файлы не перечислены среди ошибок.
- pytest: целевые `test_fbs_picking.py` и `test_fbs_packaging_integration.py` — 24 passed (прогнаны отдельными группами).
- back_guard.py: не запущен — файла `scripts/ci/back_guard.py` в этой рабочей копии нет.
- check_migrations.py: не запущен — файла `scripts/ci/check_migrations.py` в этой рабочей копии нет.
- git diff --check: пройден.

## Не реализовано

- Не добавлялись API и UI-пункты из соседних атомов. Файл `fbs_packaging_integration_service.py` не менялся: запрет списания из чужой сортировки уже реализован и покрыт тестом.

## Блокеры

Нет. Секреты, токены, `.env` и кабинеты учётных данных не читались.

# DEV · 04-warehouse-switch · screen-dev · атом 12

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/tests-e2e/ff-fbs-supply.spec.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/night/volna-9-recovery/cards/04-warehouse-switch/DEV.md`

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` (каталог `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend`) — не выполнен: в рабочей копии отсутствует `node_modules/.bin/tsc`; `npx` ожидает внешнюю установку пакета.
- `python3 scripts/ui/ui_guard.py` (корень рабочей копии) — красный. Храповик сообщает уже имеющиеся новые нарушения базовой линии, в том числе `frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx: экран-монолит 2493 → 2605`; базовую линию флагом `--update` не менял.
- `npm run test:unit` (каталог `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend`) — не выполнен: в рабочей копии отсутствует `node_modules/.bin/vitest`.
- Целевой Playwright-сценарий `ff-fbs-supply.spec.ts` — не выполнен по той же причине: отсутствует `node_modules/.bin/playwright`.
- `git diff --check` — зелёный.
- Отдельный Git-коммит не создан: Git не разрешил создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-1-04-warehouse-switch/index.lock` (`Operation not permitted`).

## Не реализовано

- Изменение экранной логики не потребовалось: в `FfFbsSupplyWorkspace.tsx` скан склада после начала подбора уже показывает `Склад закреплён: подбор уже начат` до любого сброса `pickLocation`. Исправлен пробел в проверке: E2E теперь сначала выбирает ячейку, затем сканирует другой склад и подтверждает, что следующий ожидаемый скан всё ещё товар, то есть выбранная ячейка сохранена.
- Автоматический запуск сценария не подтверждён из-за отсутствующих зависимостей frontend в этой рабочей копии.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных и боевой прод не открывались и не изменялись.
