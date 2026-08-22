## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/ui-kit/Cells.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/ui-kit/Actions.tsx` — проверен без изменений: `PrintAction what="счёт"` даёт подпись «Печать счёта».
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/ui-kit/index.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/ui-kit/Cells.test.ts`

## Гейты

- `tsc --noEmit -p tsconfig.app.json`: не запущен — в checkout отсутствует `frontend/node_modules/.bin/tsc`.
- `python3 scripts/ui/ui_guard.py`: красный из-за пяти новых/изменённых вне этого атома нарушений (`src/App.tsx`, `src/components/WbProductPickerDialog.tsx`, `src/screens/ff/FfSettingsScreen.tsx`, `src/screens/v2/FfFbsSupplyWorkspace.tsx`, `src/screens/v2/SellerInboundDraftScreen.tsx`); файлы этого атома в выводе отсутствуют, базовую линию не обновлял.
- `npm run test:unit`: не запущен — отсутствует `frontend/node_modules/.bin/vitest`.

## Не реализовано

- Находки из `REVIEW.md`, относящиеся к backend и экранным файлам биллинга, не относятся к разрешённым файлам этого атома и не изменялись.
- `PrintAction` не требовал правки: для `what="счёт"` панель уже показывает «Печать счёта».
