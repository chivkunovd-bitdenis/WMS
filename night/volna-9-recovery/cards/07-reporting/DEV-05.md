## Изменённые файлы

- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/ui-kit/MovementFlowChart.tsx
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/ui-kit/index.ts
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/ui-kit/MovementFlowChart.test.tsx

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — не выполнен: локального `tsc` нет, а `npx` не смог скачать пакет из-за сетевой ошибки `ENOTFOUND registry.npmjs.org`.
- `python3 scripts/ui/ui_guard.py` — красный из-за трёх новых нарушений в несвязанных файлах: `src/components/WbProductPickerDialog.tsx`, `src/screens/v2/FfFbsSupplyWorkspace.tsx`, `src/screens/v2/SellerInboundDraftScreen.tsx`. Файлы не изменялись и baseline не обновлялся.
- `npm run test:unit -- --run src/ui-kit/MovementFlowChart.test.tsx` — не выполнен из-за отсутствующих локальных зависимостей (`node_modules/.bin/vitest` отсутствует); запуск общей команды остановился на недоступном npm registry.

## Не реализовано

- Пункты контракта для этого атома реализованы: обычное состояние, видимая легенда, доступное описание, условная пунктирная серия сравнения, пустой период и skeleton при загрузке.
