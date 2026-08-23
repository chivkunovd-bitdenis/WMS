## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/frontend/tests-e2e/catalog-box-lookup.spec.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/night/catalog-box-lookup-20260823/cards/01-catalog-box-lookup/DEV.md`

## Гейты

- Зелёный: из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/frontend` выполнен `npx tsc --noEmit -p tsconfig.app.json`.
- Красный из-за существующих отступлений вне этого атома: из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup` выполнен `python3 scripts/ui/ui_guard.py`. Он сообщил о `src/components/WbProductPickerDialog.tsx`, `src/screens/v2/FfFbsSupplyWorkspace.tsx`, `src/screens/v2/FfProductsCatalogScreen.tsx` и `src/screens/v2/SellerInboundDraftScreen.tsx`; базовая линия не менялась.
- Красный из-за отсутствующей локальной исполняемой команды: из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/frontend` выполнен `npm run test:unit -- catalog-box-lookup`; оболочка вернула `sh: vitest: command not found`.
- Зелёный целевой E2E: из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/frontend` выполнен `npx --no-install playwright test tests-e2e/catalog-box-lookup.spec.ts -g 'catalog scan follows a received box through partial and full putaway' --reporter=line`. Сценарий проверил видимый заголовок `Приёмка №…` ровно с одним знаком номера; `Приёмка № №…` не соответствует утверждению.
- Зелёный: из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup` выполнен `git diff --check`.
- Не сохранено коммитом: команда `git add frontend/tests-e2e/catalog-box-lookup.spec.ts night/catalog-box-lookup-20260823/cards/01-catalog-box-lookup/DEV.md && git commit -m 'test: assert catalog intake number prefix'` не смогла создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-1-01-catalog-box-lookup/index.lock`: `Operation not permitted`.

## Не реализовано

Нет. Реализован только атом 4 из `FEATURES.md`: E2E-защита заголовка приёмки с единственным знаком `№`.

## Находки

Секреты, ключи, токены, `.env` и кабинеты учётных данных не открывались. Боевой сервер `194.87.96.144` не использовался.
