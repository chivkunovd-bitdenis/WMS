# 04-warehouse-switch · screen-dev

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/ui-kit/WarehouseContextSwitch.test.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/night/volna-9-recovery/cards/04-warehouse-switch/DEV.md`

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend` — зелёный.
- `npm run test:unit` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend` — зелёный. Добавлена проверка `WarningNotice` и подтверждено, что в раскрытом переключателе видны только имена складов, без их ID.
- `python3 scripts/ui/ui_guard.py` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch` — красный из-за новых нарушений в неразрешённых этим атомом файлах: `frontend/src/components/WbProductPickerDialog.tsx`, `frontend/src/screens/v2/FfFbsOrdersScreen.tsx`, `frontend/src/screens/v2/FfFbsStockSyncScreen.tsx`, `frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx`, `frontend/src/screens/v2/SellerInboundDraftScreen.tsx`. Базовая линия не менялась.

## Не реализовано

Все пункты атома реализованы буквально: `WarehouseContextSwitch` скрывается при 0–1 варианте, открывает список имён и закрывает его после выбора; loading, disabled и error состояния не позволяют совершить действие и показывают причину. `WarningNotice` показывает неблокирующее предупреждение.

## Находки

Ревью `REVIEW.md` содержит 15 замечаний к серверному коду и экранным срезам. Прямых замечаний к файлам этого ui-kit атома нет; их исправление выходит за разрешённые границы данного шага.

Git-коммит не создан: среда запретила создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-1-04-warehouse-switch/index.lock` (`Operation not permitted`). Изменения остаются в рабочем дереве и требуют коммита из среды с доступом к Git metadata.
