# DEV · 04-warehouse-switch · screen-dev

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/InboundScreen.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/OutboundScreen.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/tests-e2e/inbound-intake.spec.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/tests-e2e/outbound-submit-storage.spec.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/night/volna-9-recovery/cards/04-warehouse-switch/DEV.md`

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — не подтверждён: локальный `tsc` отсутствует, а `npx` не завершился в рабочей копии без локальных зависимостей.
- `python3 scripts/ui/ui_guard.py` — красный из-за уже существующих нарушений в соседних экранах; новых нарушений в `InboundScreen.tsx` и `OutboundScreen.tsx` нет. Для `InboundScreen.tsx` guard показывает улучшение `691 → 681` строк.
- `npm run test:unit` — красный технически: `vitest: command not found`.

Проверены сценарии S-22/S-24: при одном операционном складе `WarehouseContextSwitch` не рендерится; при нескольких он расположен до списка и формы, а выбор передаётся через `onWarehouseChange`. При открытом документе значение берётся из `inboundDetail.warehouse_id`/`outboundDetail.warehouse_id`, переключатель блокируется, и отдельного поля «Склад для заявки/отгрузки» в формах нет.

## Не реализовано

- Находки REVIEW.md по backend, `App.tsx`, FBS-подбору, упаковке, перемещениям и документации не относятся к разрешённым файлам этого screen-dev атома и не изменялись.
- Полный E2E-прогон не выполнен из-за отсутствующих локальных frontend-зависимостей; это ограничение проверки, а не изменение контракта.
