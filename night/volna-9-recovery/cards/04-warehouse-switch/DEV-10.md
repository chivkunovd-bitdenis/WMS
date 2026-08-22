## Изменённые файлы

- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/FfFbsOrdersScreen.tsx
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/night/volna-9-recovery/cards/04-warehouse-switch/DEV.md

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` из `frontend/` — зелёный.
- `python3 scripts/ui/ui_guard.py` из корня — красный: guard сообщает новые превышения монолитности в `FfFbsOrdersScreen.tsx` (1608 строк) и `FfFbsSupplyWorkspace.tsx` (2507 строк), а также нарушения в соседних файлах; базовая линия не обновлялась.
- `npm run test:unit` из `frontend/` — красный: в окружении отсутствует `vitest` (`vitest: command not found`).

## Не реализовано

- Буквальная смена склада консолидации в рабочем месте не подключена: доступный `FbsWorkspace` содержит только склад документа, а разрешённые файлы карточки не включают API-клиент или backend-контракт для передачи нового `warehouse_id`. Реализован показ контекста и блокировка смены после начала поставки.
- Новые e2e/unit-сценарии не добавлялись: unit-runner отсутствует, а изменение `fbsApi.ts` для передачи WMS-фильтра запрещено списком файлов карточки.
