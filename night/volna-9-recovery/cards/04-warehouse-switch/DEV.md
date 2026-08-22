# DEV · 04-warehouse-switch · screen-dev

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/InboundScreen.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/OutboundScreen.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/night/volna-9-recovery/cards/04-warehouse-switch/DEV.md`

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — не подтверждён: `npx` не завершился в рабочей копии без доступного локального `tsc`, процесс остановлен.
- `python3 scripts/ui/ui_guard.py` — красный из-за пяти существующих нарушений в соседних экранах: `WbProductPickerDialog.tsx`, `FfFbsOrdersScreen.tsx`, `FfFbsStockSyncScreen.tsx`, `FfFbsSupplyWorkspace.tsx`, `SellerInboundDraftScreen.tsx`. В изменённом `InboundScreen.tsx` нарушение стало меньше (`691 → 681` строк); новых нарушений в изменённых файлах guard не сообщил.
- `npm run test:unit` — не запущен: `vitest: command not found`.

## Не реализовано

- Backend-находки REVIEW.md не относятся к разрешённым файлам этого screen-dev атома и не изменялись.
- Полный живой E2E-прогон не выполнен: локальные frontend-зависимости для unit/TypeScript отсутствуют.
