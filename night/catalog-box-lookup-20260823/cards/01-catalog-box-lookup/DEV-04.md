# DEV · 01-catalog-box-lookup · атом 4

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/frontend/src/screens/v2/FfCatalogInboundPackages.tsx` — адресный результат сохраняется при обычной загрузке списка и остаётся видимым вместе со скелетоном, после ошибки и после «Повторить»; `fully_distributed` показывает состояние «Товар из короба уже разложен» независимо от статуса приёмки.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/frontend/tests-e2e/catalog-box-lookup.spec.ts` — целевой сценарий `S-16-TC-015`: полностью разложенный короб остаётся раскрытым во время первой загрузки, после её ошибки и после успешного повтора.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/night/catalog-box-lookup-20260823/cards/01-catalog-box-lookup/DEV.md` — артефакт этого атома.

## Гейты

- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/frontend && npx tsc --noEmit -p tsconfig.app.json` — команда завершилась с кодом `0` без вывода. Для исключения подмены одноимённой утилиты дополнительно выполнена `npx --yes --package typescript@~6.0.2 tsc --noEmit -p tsconfig.app.json`; также код `0`, без ошибок.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup && python3 scripts/ui/ui_guard.py` — красный из-за новых нарушений вне этого атома: `src/components/WbProductPickerDialog.tsx`, `src/screens/v2/FfFbsSupplyWorkspace.tsx`, `src/screens/v2/FfProductsCatalogScreen.tsx`, `src/screens/v2/SellerInboundDraftScreen.tsx`. Базовую линию не обновлял и чужие файлы не менял.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/frontend && npm run test:unit -- FfCatalogInboundPackages` — красный: `sh: vitest: command not found`; в рабочей копии отсутствует `frontend/node_modules/.bin/vitest`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/frontend && npm run test:e2e -- catalog-box-lookup.spec.ts` — красный: `playwright test` вызвал системный Python CLI и вернул `error: unknown command 'test'`; локальный `frontend/node_modules/.bin/playwright` отсутствует.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup && git diff --check` — зелёный.
- `git add frontend/src/screens/v2/FfCatalogInboundPackages.tsx frontend/tests-e2e/catalog-box-lookup.spec.ts night/catalog-box-lookup-20260823/cards/01-catalog-box-lookup/DEV.md && git commit -m "fix: preserve catalog box lookup result"` — не выполнен: Git не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-1-01-catalog-box-lookup/index.lock` (`Operation not permitted`). Изменения сохранены в рабочей копии, но отдельный commit SHA в этом окружении получить нельзя.

## Не реализовано

Нет. Реализован только атом 4 из `FEATURES.md`. Находки ревью о фильтре селлера и гонках сканирования относятся к отдельным атомам 5 и 6 и намеренно не затрагивались.

## Находки

Секреты, ключи, токены, `.env` и кабинеты учётных данных не открывались. Боевой сервер `194.87.96.144` не использовался.
