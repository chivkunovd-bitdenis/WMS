## Изменённые файлы

- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/frontend/src/ui-kit/UiKitShowcase.tsx

`TableLoadMore.tsx` и `index.ts` уже содержали требуемую реализацию и экспорт; по замечаниям ревьюера изменений в них не потребовалось.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — не завершён: `npx` завис на попытке получить отсутствующий локальный `tsc`, процесс остановлен.
- `python3 scripts/ui/ui_guard.py` — красный из-за пяти нарушений в соседних экранах: `MarkingPrintDialog.tsx`, `WbProductPickerDialog.tsx`, `FfFbsOrdersScreen.tsx`, `FfFbsSupplyWorkspace.tsx`, `SellerInboundDraftScreen.tsx`. Эти файлы не относятся к атомарному куску и не изменялись.
- `npm run test:unit` — красный: `vitest: command not found`.

## Не реализовано

- Новых нереализованных пунктов контракта нет. Showcase демонстрирует скрытое, доступное, загружаемое и ошибочное состояния; интерактивный пример считает вызовы и блокирует повторный вызов во время загрузки.
