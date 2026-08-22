## Изменённые файлы

- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/night/volna-9-recovery/cards/06-picking-list-order/DEV.md

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` (из `frontend/`) — зелёный.
- `python3 scripts/ui/ui_guard.py` (из корня) — зелёный.
- `npm run test:unit` (из `frontend/`) — красный: в рабочей копии нет локального `vitest` (`sh: vitest: command not found`).
- `git diff --check` — зелёный.

## Не реализовано

- Находки 1 и 2 относятся к `/frontend/src/screens/v2/FfFbsPickList.tsx`, который не входит в атом 5; они требуют отдельной доработки печатного окна и состава ленты с Честным знаком.
- Находка 3 относится к серверной проверке полного состава в `/backend/app/services/fbs_order_tape_print_service.py`; этот backend-слой не входит в атом 5.
- Находка 4 уже устранена серверным атомом 4: endpoint `print-assets` возвращает `wb_order_id` и `order_number`, которые существующий `FbsPrintPreviewDialog.tsx` показывает и использует для служебной этикетки. В этом атоме новых правок для него не потребовалось.
- Находка 5 требует Playwright-сценариев и относится к следующему атому 6; автоматический unit-gate сейчас не запускается из-за отсутствующего `vitest`.
