# DEV · 04-warehouse-switch · атом 1

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/App.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/ff/FfPackagingPage.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/ff/FfPackagingPage.test.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/night/volna-9-recovery/cards/04-warehouse-switch/DEV.md`

## Гейты

- ЗЕЛЁНЫЙ — `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend && npx tsc --noEmit -p tsconfig.app.json` (exit 0).
- КРАСНЫЙ ИЗ-ЗА РАНЕЕ ЗАКОММИЧЕННЫХ ФАЙЛОВ ВНЕ ГРАНИЦ АТОМА — `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch && python3 scripts/ui/ui_guard.py` (exit 1). В разрешённых файлах новых нарушений нет: guard сообщает `src/App.tsx: экран-монолит 3492 → 3491` и `src/screens/ff/FfPackagingPage.tsx: экран-монолит 2146 → 2143` как «стало лучше». Красный остаток относится к `src/components/WbProductPickerDialog.tsx`, `src/screens/v2/FfFbsOrdersScreen.tsx`, `src/screens/v2/FfFbsStockSyncScreen.tsx`, `src/screens/v2/FfFbsSupplyWorkspace.tsx` и `src/screens/v2/SellerInboundDraftScreen.tsx`; эти файлы не изменены данным атомом и запрещены роли `screen-dev`.
- ЗЕЛЁНЫЙ — `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend && npm run test:unit -- src/screens/ff/FfPackagingPage.test.ts` (2 теста пройдены, exit 0).
- ЗЕЛЁНЫЙ — `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch && git diff --check` (exit 0).
- КРАСНЫЙ ИЗ-ЗА ОГРАНИЧЕНИЯ SANDBOX — `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch && git add frontend/src/App.tsx frontend/src/screens/ff/FfPackagingPage.tsx frontend/src/screens/ff/FfPackagingPage.test.ts night/volna-9-recovery/cards/04-warehouse-switch/DEV.md && git diff --cached --check && git diff --cached --name-only && git commit -m "fix(packaging): use shared warehouse context"` (exit 128): Git не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-1-04-warehouse-switch/index.lock`, `Operation not permitted`.

## Не реализовано

- Поведение атома реализовано буквально: S-14 получает общий список складов, выбранный `warehouse_id` и обработчик смены из `App`; локального экземпляра `useWarehouseContext` на странице нет; `WarehouseContextSwitch` показан при двух складах; при `null` остаётся существующее пустое состояние и запрос очереди не выполняется.
- Сделать общий `ui_guard.py` зелёным в этой рабочей копии не удалось без правок пяти соседних файлов вне разрешённого списка. Базовая линия не обновлялась, чужие файлы не правились.
- Сохранить результат отдельным Git-коммитом не удалось: sandbox разрешает менять файлы worktree, но запрещает запись в общий Git-каталог зарегистрированного worktree. Второй checkout, клон или временный репозиторий не создавался.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных и боевой production не открывались и не изменялись.
