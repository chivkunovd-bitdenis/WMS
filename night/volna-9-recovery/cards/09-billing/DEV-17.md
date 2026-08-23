## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/screens/ff/FfSettingsScreen.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/screens/ff/FfSettingsScreen.test.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/night/volna-9-recovery/cards/09-billing/DEV.md`

В форме новой ставки хранение жёстко использует `liter_day`; при возврате на
приёмку или отгрузку форма сохраняет допустимые `document` либо `item`, а при
устаревшей недопустимой паре запрос вообще не формируется. В списке вариантов
операционных услуг «За литр-день» больше не предлагается.

## Гейты

- Зелёный: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend && npx tsc --noEmit -p tsconfig.app.json`.
- Зелёный: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend && npm run test:unit -- src/screens/ff/FfSettingsScreen.test.ts` — 1 файл, 4 теста passed. Проверены переходы хранение → приёмка/отгрузка, сохранение допустимых пар и отказ от `liter_day` у операционной услуги.
- Красный вне границ атома: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing && python3 scripts/ui/ui_guard.py`. Сторож считает 643 строки в `FfSettingsScreen.tsx`, что улучшает базовую границу 701. Завершению с кодом 1 мешают только не относящиеся к атому файлы: `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/components/WbProductPickerDialog.tsx`, `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx` и `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/screens/v2/SellerInboundDraftScreen.tsx`. Базовая линия не изменялась.

## Не реализовано

Нет. Все пункты атома 17 и находка 12 из `REVIEW.md`, относящаяся к этому экрану, реализованы буквально.

## Находки

Секреты, ключи, токены, `.env`, кабинеты учётных данных и боевой прод не читались и не изменялись.

Git-сохранение не выполнено: `git add` не смог создать
`/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-3-09-billing1/index.lock`
из-за `Operation not permitted`. Изменения остаются в рабочей копии и не имеют
восстановимого commit SHA.
