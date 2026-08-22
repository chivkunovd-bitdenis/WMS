# DEV · 04-warehouse-switch

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/ui-kit/WarehouseContextSwitch.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/ui-kit/WarningNotice.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/ui-kit/index.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/ui-kit/WarehouseContextSwitch.test.tsx`

Компоненты и тесты уже соответствуют контракту: выбор скрыт при одном складе, при двух и более открывается по клику, показывает только имена, вызывает `onChange` и закрывается; loading, error и disabled-состояния объясняют причину и блокируют действие. `WarningNotice` экспортируется из ui-kit как неблокирующее предупреждение.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — красный: локальный `tsc` отсутствует, `npx` попытался скачать пакет и получил `ENOTFOUND registry.npmjs.org`.
- `python3 scripts/ui/ui_guard.py` — красный из-за пяти предварительно существующих нарушений в соседних экранах: `WbProductPickerDialog.tsx`, `FfFbsOrdersScreen.tsx`, `FfFbsStockSyncScreen.tsx`, `FfFbsSupplyWorkspace.tsx`, `SellerInboundDraftScreen.tsx`. В ui-kit новых нарушений не выявлено; базовую линию не обновлял.
- `npm run test:unit -- --run src/ui-kit/WarehouseContextSwitch.test.tsx` — красный: `vitest: command not found`, зависимости frontend не установлены.

## Не реализовано

- Находки 1–16 из `REVIEW.md` относятся к backend или конкретным продуктовым экранам и не относятся к четырём файлам этого ui-kit-атома; по границам роли `screen-dev` они не менялись.
- Полный запуск TypeScript и unit-тестов невозможен без локальных frontend-зависимостей и сетевого доступа к npm registry.
