# DEV · 07-reporting · атом 5

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/ui-kit/MovementFlowChart.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/ui-kit/MovementFlowChart.test.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/night/volna-9-recovery/cards/07-reporting/DEV.md`

## Гейты

- Зелёный: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend && npx tsc --noEmit -p tsconfig.app.json`.
- Красный: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting && python3 scripts/ui/ui_guard.py`. Новые нарушения зафиксированы в чужих файлах вне атома: `frontend/src/App.tsx`, `frontend/src/components/WbProductPickerDialog.tsx`, `frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx`, `frontend/src/screens/v2/SellerInboundDraftScreen.tsx`. Базовая линия не обновлялась.
- Красный: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend && npm run test:unit -- src/ui-kit/MovementFlowChart.test.tsx --run`. Причина: `sh: vitest: command not found`; зависимости для frontend не установлены в этой рабочей копии.

Точная команда, выполненная ранее в составе связанной проверки: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend && npx tsc --noEmit -p tsconfig.app.json && npm run test:unit -- MovementFlowChart.test.tsx`.

## Не реализовано

Нет. Находка review №7, относящаяся к этому атому, исправлена: график теперь показывает пустое состояние и для непустой дневной серии, в которой все отображаемые значения равны нулю, а не рисует нулевые линии.

## Находки

- `ui_guard.py` обнаружил новые нарушения вне разрешённых файлов атома; они не изменялись.
- Установленные frontend-зависимости отсутствуют, поэтому Vitest не запускается.
