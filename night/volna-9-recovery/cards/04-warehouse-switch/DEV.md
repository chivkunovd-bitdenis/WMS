# screen-dev · 04-warehouse-switch

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/ui-kit/WarehouseContextSwitch.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/ui-kit/WarningNotice.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/ui-kit/index.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/ui-kit/WarehouseContextSwitch.test.tsx`

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — зелёный, команда завершилась с кодом 0.
- `python3 scripts/ui/ui_guard.py` — красный: обнаружены новые нарушения в соседних файлах `src/components/WbProductPickerDialog.tsx`, `src/screens/v2/FfFbsOrdersScreen.tsx`, `src/screens/v2/FfFbsStockSyncScreen.tsx`, `src/screens/v2/FfFbsSupplyWorkspace.tsx`, `src/screens/v2/SellerInboundDraftScreen.tsx`; эти файлы не входят в атом и не изменялись.
- `npm run test:unit` — красный: `vitest: command not found`, локальные зависимости отсутствуют.

## Не реализовано

Замечания `REVIEW.md` относятся к backend и соседним экранам; они не входят в слой этого атома и не изменялись по границам роли `screen-dev`. Проверка `ui_guard.py` также выявила нарушения в соседних экранах, которые нельзя исправлять в этой карточке.
