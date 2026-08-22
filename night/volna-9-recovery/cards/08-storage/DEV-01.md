## Изменённые файлы

- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend/src/ui-kit/Actions.tsx
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend/src/ui-kit/Actions.test.tsx

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — зелёный, ошибок TypeScript не вывел.
- `python3 scripts/ui/ui_guard.py` — красный из-за трёх новых нарушений в посторонних файлах: `frontend/src/components/WbProductPickerDialog.tsx`, `frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx`, `frontend/src/screens/v2/SellerInboundDraftScreen.tsx`. Изменённые файлы этого атома в выводе не названы; базовую линию не обновлял.
- `npm run test:unit -- --run src/ui-kit/Actions.test.tsx` — не запущен: `vitest: command not found`.

## Не реализовано

- Невыполненные пункты контракта для этого атома отсутствуют. Внутренняя подпись `накладную` теперь отображается как «Печать накладной» в вариантах `row` и `panel`; публичный интерфейс `PrintAction` не менялся.
- Находки ревью по экрану хранения и backend не относятся к разрешённым файлам этого атома и не изменялись.
