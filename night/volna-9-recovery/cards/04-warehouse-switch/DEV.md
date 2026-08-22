# DEV · 04-warehouse-switch · feature 5

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/utils/fbsWarehouse.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/utils/fbsWarehouse.test.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/contexts/WarehouseContext.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/App.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/apps/seller/SellerApp.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/night/volna-9-recovery/cards/04-warehouse-switch/DEV.md`

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` из `frontend/` — зелёный.
- `python3 scripts/ui/ui_guard.py` из корня — красный: новые нарушения уже находятся в не затронутых этим атомом `src/components/WbProductPickerDialog.tsx`, `src/screens/v2/FfFbsOrdersScreen.tsx`, `src/screens/v2/FfFbsStockSyncScreen.tsx`, `src/screens/v2/FfFbsSupplyWorkspace.tsx`, `src/screens/v2/SellerInboundDraftScreen.tsx`. Базовая линия не менялась.
- `npm run test:unit -- fbsWarehouse.test.ts` из `frontend/` — не запущен: `vitest: command not found` (в рабочей копии отсутствуют установленные frontend-зависимости).
- `git diff --check` — зелёный.
- Commit не создан: Git не имеет права создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-1-04-warehouse-switch/index.lock` (`Operation not permitted`). Изменения остаются в рабочем дереве.

## Не реализовано

- Находки REVIEW №1–15, кроме границ общего сессионного контекста, относятся к следующим атомам и их экранным/серверным файлам. В этом атоме устранены неявный выбор первого операционного склада, наследование контекста между разными пользователями и применение контекста ФФ как глобального фильтра портала селлера.
- Полный запуск unit-тестов невозможен без `vitest` в `frontend/node_modules`; новый тест `fbsWarehouse.test.ts` добавлен, но не выполнен в этой рабочей копии.
