## Изменённые файлы

- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/fbsApi.ts
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/FbsSupplyCreateDialog.tsx
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/night/volna-9-recovery/cards/04-warehouse-switch/DEV.md

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — зелёный (команда завершилась без диагностик).
- `python3 scripts/ui/ui_guard.py` — красный из-за существующих нарушений в соседних экранах и нового ограничения монолита/стилей этого экрана; базовая линия не обновлялась.
- `npm run test:unit -- --run src/screens/v2/FbsSupplyCreateDialog.test.ts` — красный: в окружении отсутствует команда `vitest` (`vitest: command not found`).

## Не реализовано

- В контрактном списке складских строк оставлена обратная совместимость: если backend не вернул `inventory`, `warehouse_options` или `recommended_warehouse`, диалог сохраняет прежний summary без выдуманных остатков.
- Живой браузерный e2e не запускался, поскольку обязательный unit-runner отсутствует в окружении; существующий e2e-файл не изменялся, так как его сценарии требуют backend-полей и относятся к следующему интеграционному проходу.
