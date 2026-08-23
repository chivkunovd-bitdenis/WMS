# Screen-dev · 01-catalog-box-lookup · атом 8

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/frontend/tests-e2e/catalog-box-lookup.spec.ts` — остаток проверяется через конкретную строку таблицы состава и её ячейку `QtyCell`, а не по произвольной цифре в accordion; добавлен сценарий `S-16-TC-017` для фильтра селлера A и адресного скана короба селлера B с проверками SKU, названия, ШК и остатка.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/night/catalog-box-lookup-20260823/cards/01-catalog-box-lookup/DEV.md` — отчёт атома 8.

## Гейты

- Зелёный: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/frontend && npx tsc --noEmit -p tsconfig.app.json` — код возврата `0`, диагностик нет.
- Красный вне слоя атома: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup && python3 scripts/ui/ui_guard.py` — новые отступления уже есть в чужих файлах `frontend/src/components/WbProductPickerDialog.tsx`, `frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx`, `frontend/src/screens/v2/FfProductsCatalogScreen.tsx`, `frontend/src/screens/v2/SellerInboundDraftScreen.tsx`. Базовая линия не обновлялась.
- Красный, ограничение окружения: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/frontend && npm run test:unit -- catalog-box-lookup` — `sh: vitest: command not found`; локальный `vitest` отсутствует.
- Зелёный: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/frontend && npx playwright test tests-e2e/catalog-box-lookup.spec.ts --grep 'catalog scan follows|catalog ignores'` — код возврата `0`; выполнены сценарии остатка/повтора списка/фильтра селлера и позднего отказа первого lookup.
- Зелёный: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup && git diff --check` — ошибок пробелов нет.
- Не сохранено commit: `git add frontend/tests-e2e/catalog-box-lookup.spec.ts night/catalog-box-lookup-20260823/cards/01-catalog-box-lookup/DEV.md && git commit -m "test: strengthen catalog box lookup e2e"` не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-1-01-catalog-box-lookup/index.lock` (`Operation not permitted`). Поэтому проверенного SHA нет.

## Не реализовано

Нет. Реализован только атом 8 из `FEATURES.md`; продуктовые файлы и соседние задачи не менялись.

## Находки

Секреты, ключи, токены, `.env` и кабинеты учётных данных не открывались. Боевой сервер `194.87.96.144` не использовался.
