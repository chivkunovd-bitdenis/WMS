# DEV · 04-warehouse-switch

## Изменённые файлы

- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/utils/fbsWarehouse.ts
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/App.tsx
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/apps/seller/SellerApp.tsx
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/night/volna-9-recovery/cards/04-warehouse-switch/DEV.md

Изменения сохраняют операционный склад в сессионном контексте, выбирают первичный склад при его наличии, исключают служебные `FBS WB *`, очищают контекст при выходе и передают обработчик переключения в приёмку и отгрузку. Подстановки `warehouses[0]` в разрешённых файлах убраны.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — красный: локального `tsc` нет; `npx --no-install` не смог найти бинарник и попытался обратиться к `registry.npmjs.org`, сеть недоступна (`ENOTFOUND`).
- `python3 scripts/ui/ui_guard.py` — красный: зафиксированы новые нарушения в соседних файлах, не изменённых этой карточкой: `src/components/WbProductPickerDialog.tsx`, `src/screens/v2/FfFbsOrdersScreen.tsx`, `src/screens/v2/FfFbsStockSyncScreen.tsx`, `src/screens/v2/FfFbsSupplyWorkspace.tsx`, `src/screens/v2/SellerInboundDraftScreen.tsx`. Baseline не обновлялся.
- `npm run test:unit` — красный: `vitest: command not found`, зависимости фронтенда в рабочей копии не установлены.

## Не реализовано

- Переключение склада внутри `FfFbsSupplyWorkspace` из находки REVIEW не исправлялось: этот экран не входит в разрешённые файлы атома; редактирование соседнего экрана нарушило бы границы роли `screen-dev`.
- Требуемые проверки не стали зелёными из-за отсутствующих локальных инструментов/зависимостей и несвязанных нарушений `ui_guard.py`; исправлять их через изменение baseline запрещено инструкцией роли.
