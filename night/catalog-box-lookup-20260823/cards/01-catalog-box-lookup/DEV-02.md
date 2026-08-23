## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/frontend/tests-e2e/catalog-box-lookup.spec.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/night/catalog-box-lookup-20260823/cards/01-catalog-box-lookup/DEV.md`

## Гейты

- Зелёный: из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/frontend` выполнен `npx tsc --noEmit -p tsconfig.app.json`.
- Красный из-за уже существующих отступлений вне атома: из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup` выполнен `python3 scripts/ui/ui_guard.py`. Он сообщил о `src/components/WbProductPickerDialog.tsx`, `src/screens/v2/FfFbsSupplyWorkspace.tsx`, `src/screens/v2/FfProductsCatalogScreen.tsx` и `src/screens/v2/SellerInboundDraftScreen.tsx`; базовая линия не менялась.
- Красный из-за отсутствующей локальной исполняемой команды: из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/frontend` выполнен `npm run test:unit -- catalog-box-lookup`; оболочка вернула `sh: vitest: command not found`.
- Зелёный целевой E2E: из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/frontend` выполнен `npx --no-install playwright test tests-e2e/catalog-box-lookup.spec.ts -g 'catalog scan follows a received box through partial and full putaway|catalog ignores a late failed scan after the operator starts the next barcode|catalog deduplicates repeated scans while the first lookup is pending' --reporter=line`. Проверены `S-16-TC-013`, `S-16-TC-014`, `S-16-TC-016` и относящиеся регрессии.
- Зелёный: из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup` выполнен `git diff --check`.
- Не сохранено коммитом: `git add frontend/tests-e2e/catalog-box-lookup.spec.ts night/catalog-box-lookup-20260823/cards/01-catalog-box-lookup/DEV.md` не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-1-01-catalog-box-lookup/index.lock` (`Operation not permitted`). Изменения остаются в рабочей копии без проверенного SHA.

## Не реализовано

Для атома 2 — нет. Находки review по ожиданию повтора ленивого списка, полноте проверки полностью разложенного короба и заголовку приёмки относятся к другим сценариям, а не к гонке адресных сканов; в этот атом не включались.

## Находки

Нет.
