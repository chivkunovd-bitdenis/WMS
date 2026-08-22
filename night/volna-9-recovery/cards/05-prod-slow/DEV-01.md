# DEV · 05-prod-slow · экран S-03 · атом 1

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/frontend/src/screens/v2/FfFbsOrdersScreen.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/frontend/tests-e2e/ff-fbs-orders.spec.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/night/volna-9-recovery/cards/05-prod-slow/DEV.md`

В таблице вкладки «Новые» закреплена табличная раскладка и ширина 713 px
(48 px служебной колонки чекбокса + 210 / 135 / 180 / 140 px четырёх
информационных колонок). Четыре заголовка остаются `nowrap`. Ремонтный E2E
сценарий теперь проверяет фиксированную раскладку, ширину таблицы, отсутствие
переноса заголовков и отсутствие удалённой жёлтой заливки как до hover, так и
во время hover.

## Гейты

- Зелёный: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/frontend && npx tsc --noEmit -p tsconfig.app.json`.
- Красный, существующие baseline-нарушения, baseline не менялся: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow && python3 scripts/ui/ui_guard.py`. Вывод: `MarkingPrintDialog.tsx` 1687 → 1750, `WbProductPickerDialog.tsx` 0 → 646, `FfFbsOrdersScreen.tsx` 1587 → 1667, `FfFbsSupplyWorkspace.tsx` 2493 → 2498, `SellerInboundDraftScreen.tsx` 1111 → 1169. Исправление этих монолитов и обновление baseline выходят за границы атома; флаг `--update` не применялся.
- Зелёный: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/frontend && npm run test:unit` — 20 файлов, 142 теста.
- Не выполнен из-за ограничений песочницы, а не падения проверки: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/frontend && npx playwright test tests-e2e/ff-fbs-orders.spec.ts --grep 'fbs orders: search keeps list, selected drawer stays stable and Excel downloads'`. Playwright webServer не смог привязать API к `127.0.0.1:18000`: `operation not permitted`.

## Не реализовано

Нет пунктов текущего атома, которые не удалось реализовать буквально.

Находка: секреты, токены, `.env`, кабинеты учётных данных, боевой прод и живой
кабинет Wildberries не открывались и не затрагивались.
