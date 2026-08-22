# DEV · 05-prod-slow · атом 2: поиск без жёлтой заливки

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/frontend/tests-e2e/ff-fbs-orders.spec.ts` — сценарий S-03-TC-016 теперь проверяет фактические фиксированные ширины четырёх колонок вкладки «Новые», а также отсутствие жёлтого фона у результата поиска в обычном и hover-состоянии.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/night/volna-9-recovery/cards/05-prod-slow/DEV.md` — артефакт выполнения атома.

`/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/frontend/src/screens/v2/FfFbsOrdersScreen.tsx` дополнительно не менялся: требуемая ветка жёлтой заливки уже отсутствует, а `scrollMarginBottom: '220px'` и `registerRow` сохранены. Таблица уже использует `tableLayout: 'fixed'` и ширину 713px, заголовки имеют 210 / 135 / 180 / 140px и `whiteSpace: 'nowrap'`.

## Гейты

- Зелёный: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/frontend && npx tsc --noEmit -p tsconfig.app.json`.
- Зелёный: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/frontend && npm run test:unit -- src/screens/v2/fbsApi.test.ts` — 1 файл, 5 тестов.
- Красный, без изменения baseline: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow && python3 scripts/ui/ui_guard.py`. Новые относительно baseline нарушения: `src/components/MarkingPrintDialog.tsx` 1687 → 1750, `src/components/WbProductPickerDialog.tsx` 0 → 646, `src/screens/v2/FfFbsOrdersScreen.tsx` 1587 → 1667, `src/screens/v2/FfFbsSupplyWorkspace.tsx` 2493 → 2498, `src/screens/v2/SellerInboundDraftScreen.tsx` 1111 → 1169. Базовую линию флагом `--update` не менял по правилу роли.
- Не запущен до теста: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/frontend && npx playwright test tests-e2e/ff-fbs-orders.spec.ts -g 'fbs orders: search keeps list, selected drawer stays stable and Excel downloads'`. Веб-сервер не смог привязаться к `127.0.0.1:18000`: `operation not permitted`.
- Зелёный: `git diff --check`.

## Не реализовано

- Нет. В границах атома устранены относящиеся к нему находки REVIEW.md: сценарий больше не закрепляет жёлтую подсветку и проверяет фактические фиксированные ширины. Находка о модалке печати относится к следующему атому; глобальный `inventory.generated.ts` в текущем diff не изменён.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных, боевой прод и живой кабинет Wildberries не читались и не затрагивались.
