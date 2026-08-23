# 09-billing — screen-dev, атом 2

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/screens/ff/FfSettingsScreen.tsx` — действующая ставка и версии в истории выводятся общим `MoneyCell`; история открывается в штатном диалоге и закрывается иконкой закрытия с подсказкой.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/tests-e2e/billing-tariffs.spec.ts` — сценарии проверяют дробную ставку в формате `45,50 ₽`, версии в диалоге и штатное закрытие без изменения списка.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/night/volna-9-recovery/cards/09-billing/DEV.md` — отчёт реализации и проверок этого атома.

Реализация двух экранных файлов уже сохранена в истории текущей ветки коммитом `b342da77` (`night(09-billing): atom 2/6`). В этой итерации повторно проверены все относящиеся к атому находки R-08 и R-31 из `DESIGN-REVIEW.md`.

## Гейты

- Зелёный: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend && npm run test:unit -- src/screens/ff/FfSettingsScreen.test.ts` — 1 test passed.
- Красный: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend && npx tsc --noEmit -p tsconfig.app.json` — ошибки находятся в уже затронутом соседними атомами `/frontend/src/screens/ff/FfBillingScreen.tsx`, а также в существующих частях `FfSettingsScreen.tsx`, `SellersScreen.tsx` и `PeriodPicker.tsx`; новая денежная ячейка и диалог истории ошибок TypeScript не добавили.
- Красный: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing && python3 scripts/ui/ui_guard.py` — новые записи храповика: экран-монолит `FfSettingsScreen.tsx: 701 → 795` и три экрана вне атома. Базовая линия флагом `--update` не менялась.
- Не запущен: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend && npx playwright test tests-e2e/billing-tariffs.spec.ts` — Playwright выбрал только сценарии этого атома и регрессию зависимости, но webServer не смог привязаться к `127.0.0.1:18000`: `operation not permitted`.

## Не реализовано

- Ничего в пределах атома 2: R-08 исправлен общим `MoneyCell`, R-31 — штатным диалогом и иконкой закрытия. Исправление экранного монолита `FfSettingsScreen.tsx` выходит за границы одного атома и не выполнялось.

## Находки

- Секреты, ключи, токены, `.env` и кабинеты учётных данных не открывались.
