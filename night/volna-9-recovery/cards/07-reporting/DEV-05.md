# screen-dev · 07-reporting · MovementFlowChart

## Изменённые файлы

Код атома не изменён: `MovementFlowChart` уже реализован в разрешённых файлах и соответствует контракту. Проверены:

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/ui-kit/MovementFlowChart.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/ui-kit/index.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/ui-kit/MovementFlowChart.test.tsx`

Артефакт проверки записан в этот файл:

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/night/volna-9-recovery/cards/07-reporting/DEV.md`

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — не выполнен: в рабочей копии отсутствует локальный `frontend/node_modules/.bin/tsc`, запуск `npx` не предоставил локальный TypeScript.
- `python3 scripts/ui/ui_guard.py` — красный из-за трёх новых нарушений в соседних, не разрешённых этим атомом файлах: `src/components/WbProductPickerDialog.tsx`, `src/screens/v2/FfFbsSupplyWorkspace.tsx`, `src/screens/v2/SellerInboundDraftScreen.tsx`. Базовая линия не изменялась.
- `npm run test:unit -- --run src/ui-kit/MovementFlowChart.test.tsx` — не выполнен: отсутствует локальный `frontend/node_modules/.bin/vitest` (`sh: vitest: command not found`).

Проверка реализации и теста подтверждает: видимая легенда содержит приход и расход; предыдущий расход добавляется только при `showPrevious`; пустой набор показывает «За выбранный период движений нет»; загрузка показывает скелет и не рисует серии.

## Не реализовано

Невыполненных пунктов контракта для `MovementFlowChart` нет. Замечание ревьюера о передаче процентного `delta` и прошлой серии относится к `FfReportsPage` и находится вне файлов и слоя этого атома; соседние продуктовые файлы не изменялись.
