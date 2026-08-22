## Изменённые файлы

Изменений в исходном коде нет: `WarningNotice` уже реализован буквально по контракту в следующих файлах:

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/ui-kit/States.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/ui-kit/index.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/ui-kit/States.test.tsx`

Восстановлен этот отчётный артефакт:

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/night/volna-9-recovery/cards/07-reporting/DEV.md`

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` (из `frontend/`) — зелёный.
- `python3 scripts/ui/ui_guard.py` (из корня) — красный: три новых нарушения вне атома — `src/components/WbProductPickerDialog.tsx`, `src/screens/v2/FfFbsSupplyWorkspace.tsx`, `src/screens/v2/SellerInboundDraftScreen.tsx`. Для `src/screens/ff/FfReportsPage.tsx` guard зафиксировал улучшение: собственные кнопка и таблица устранены. Базовая линия не обновлялась.
- `npm run test:unit -- --run src/ui-kit/States.test.tsx` (из `frontend/`) — не запущен: `vitest: command not found`.

## Не реализовано

Ничего из атома `WarningNotice` не осталось нереализованным. Замечания из `REVIEW.md` относятся к другим карточкам и слоям; файлы за пределами контракта этого атома не изменялись.
