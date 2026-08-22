## Изменённые файлы

- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/src/screens/v2/FbsPrintPreviewDialog.tsx

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — красный: в рабочей копии отсутствует локальный `tsc`, а сеть недоступна для загрузки пакета (`ENOTFOUND registry.npmjs.org`).
- `python3 scripts/ui/ui_guard.py` — красный из-за существующих нарушений вне атома: `frontend/src/components/WbProductPickerDialog.tsx` и `frontend/src/screens/v2/SellerInboundDraftScreen.tsx`. Для затронутого `FfFbsSupplyWorkspace.tsx` нового нарушения после правки нет.
- `npm run test:unit` — красный: отсутствует локальный `vitest` (`sh: vitest: command not found`).

## Не реализовано

- Полный Playwright-сценарий из контракта не запускался: frontend-зависимости в этой рабочей копии не установлены.
- Физическая серверная выдача полных ID и полей порядка не изменялась: атом ограничен тремя frontend-файлами, указанными в контракте.
