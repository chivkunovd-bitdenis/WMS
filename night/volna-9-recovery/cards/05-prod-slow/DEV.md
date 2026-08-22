# DEV · 05-prod-slow · атом 7

## Изменённые файлы

- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/frontend/src/components/MarkingPrintDialog.tsx
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/frontend/src/utils/printMarkingCodeLabel.ts

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — не подтверждён: локальный `frontend/node_modules/.bin/tsc` отсутствует, запуск `npx` завис без результата и был остановлен.
- `python3 scripts/ui/ui_guard.py` — красный из-за уже существующих/вне атома нарушений: `MarkingPrintDialog.tsx:1687–1741`, а также `WbProductPickerDialog.tsx`, `FfFbsOrdersScreen.tsx`, `FfFbsSupplyWorkspace.tsx`, `SellerInboundDraftScreen.tsx`. Базовая линия не обновлялась.
- `npm run test:unit` — не запущен: `vitest: command not found`.
- `git diff --check` — зелёный.

Изменения проверены после финальной правки: popup создаётся только обработчиком явного открытия готовой ленты.

## Не реализовано

- Полный Playwright-путь `S-03-TC-008`, `S-03-TC-009`, `S-03-TC-014`, `S-03-TC-015` локально не подтверждён: зависимости фронтенда отсутствуют.
- Серверная дедупликация активного задания, SQLite-индекс и очереди Celery не изменялись: они относятся к backend/infra-слою и не входят в разрешённые файлы атома.
- UI-guard не исправлялся через `--update`, поскольку найденные нарушения не созданы этим атомом полностью и обновление базовой линии запрещено ролью.
