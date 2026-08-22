## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/ui-kit/Cells.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/ui-kit/Actions.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/ui-kit/index.ts`

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — не получил вывод и не завершился за ожидание; остановлен вручную.
- `python3 scripts/ui/ui_guard.py` — красный из-за существующих нарушений вне этой карточки: `src/components/WbProductPickerDialog.tsx`, `src/screens/v2/FfFbsSupplyWorkspace.tsx`, `src/screens/v2/SellerInboundDraftScreen.tsx`.
- `npm run test:unit` — не запустился: `vitest: command not found`.

## Не реализовано

- Остальные части контракта 09-billing не реализовывались: эта карточка ограничена атомом `MoneyCell` и расширением `PrintAction` для счёта.
