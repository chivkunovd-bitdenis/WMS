## Изменённые файлы

- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/screens/ff/FfSettingsScreen.tsx
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/screens/v2/SellersScreen.tsx
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/ui-kit/PeriodPicker.tsx
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/night/volna-9-recovery/cards/09-billing/DEV.md

## Гейты

- Зелёный: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend && npx tsc --noEmit -p tsconfig.app.json`.
- Зелёный: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend && npm run build` — TypeScript и production-бандл Vite собраны успешно; Vite вывел только предупреждение о размере уже существующих чанков.
- Зелёный: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend && npm run test:unit -- src/screens/ff/FfSettingsScreen.test.ts src/ui-kit/Cells.test.ts` — 2 файла, 2 теста passed.
- Красный, базовая линия не менялась: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing && python3 scripts/ui/ui_guard.py`. Сторож сообщает превышения, уже существующие вне атома: `src/components/WbProductPickerDialog.tsx` 0 → 646, `src/screens/v2/FfFbsSupplyWorkspace.tsx` 2493 → 2498, `src/screens/v2/SellerInboundDraftScreen.tsx` 1111 → 1169; также у разрешённого S-19 зафиксированное до этого атома превышение `src/screens/ff/FfSettingsScreen.tsx` 701 → 799. Последнее не связано с заменой устаревших свойств MUI (до правки файл уже был больше порога); сокращение всего экрана не входит в атом восстановления типовой сборки. Флаг `--update` не применялся.
- Не сохранено новым Git-коммитом: `git add … && git commit -m 'fix(09-billing): restore MUI form typing'` не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-3-09-billing1/index.lock` (`Operation not permitted`). Исходные изменения и этот артефакт остаются в рабочей копии.

## Не реализовано

В рамках атома не осталось нереализованных требований: устаревшие свойства MUI заменены на `slotProps`, неиспользуемый импорт удалён, прежние `data-testid` полей сохранены. Также устранены относящиеся к этой форме находки ревью: при возврате с хранения расчёт снова становится допустимым, а сетевые ошибки сохранения реквизитов и тарифа видны пользователю. Отдельный commit SHA не получен из-за запрета среды на Git lock; поэтому результат локально реализован, но не сохранён в новом коммите.
