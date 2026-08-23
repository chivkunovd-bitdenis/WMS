# Фича 1

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/frontend/tests-e2e/catalog-box-lookup.spec.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/night/catalog-box-lookup-20260823/cards/01-catalog-box-lookup/DEV.md`

## Гейты

- Зелёный: из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/frontend` выполнен `npx tsc --noEmit -p tsconfig.app.json`.
- Красный из-за уже имеющихся отступлений вне файла атома: из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup` выполнен `python3 scripts/ui/ui_guard.py`; он сообщил о `src/components/WbProductPickerDialog.tsx`, `src/screens/v2/FfFbsSupplyWorkspace.tsx`, `src/screens/v2/FfProductsCatalogScreen.tsx` и `src/screens/v2/SellerInboundDraftScreen.tsx`. Эти файлы не входят в разрешённый атом, базовая линия не менялась.
- Красный из-за отсутствующей локальной зависимости: из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/frontend` выполнен `npm run test:unit -- catalog-box-lookup`; оболочка вернула `vitest: command not found`.
- Зелёный целевой E2E: из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/frontend` выполнен `npx --no-install playwright test tests-e2e/catalog-box-lookup.spec.ts -g 'catalog scan follows a received box through partial and full putaway' --reporter=line`.
- Зелёный: `git diff --check`.
- Не сохранено отдельным коммитом: `git add frontend/tests-e2e/catalog-box-lookup.spec.ts night/catalog-box-lookup-20260823/cards/01-catalog-box-lookup/DEV.md && git commit -m "test: wait for catalog box retry result"` не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-1-01-catalog-box-lookup/index.lock` (`Operation not permitted`). Изменения остаются в рабочей копии без проверенного SHA.

## Не реализовано

Нет. Для атома 1 добавлено ожидание успешного второго `GET /operations/inbound-packages` и скрытия скелетона до проверки сохранённого адресного результата. Находки review №2–№5 принадлежат следующим атомам из `FEATURES.md` и намеренно не затрагивались.

## Находки

Нет.

# Фича 2

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

# Фича 3

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/frontend/tests-e2e/catalog-box-lookup.spec.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/night/catalog-box-lookup-20260823/cards/01-catalog-box-lookup/DEV.md`

## Гейты

- Зелёный: из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/frontend` выполнен `npx tsc --noEmit -p tsconfig.app.json`.
- Красный из-за существующих отступлений вне этого атома: из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup` выполнен `python3 scripts/ui/ui_guard.py`. Он сообщил о `src/components/WbProductPickerDialog.tsx`, `src/screens/v2/FfFbsSupplyWorkspace.tsx`, `src/screens/v2/FfProductsCatalogScreen.tsx` и `src/screens/v2/SellerInboundDraftScreen.tsx`; базовая линия не менялась.
- Красный из-за отсутствующей локальной исполняемой команды: из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/frontend` выполнен `npm run test:unit -- catalog-box-lookup`; оболочка вернула `sh: vitest: command not found`.
- Зелёный целевой E2E: из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/frontend` выполнен `npx --no-install playwright test tests-e2e/catalog-box-lookup.spec.ts -g 'catalog scan follows a received box through partial and full putaway' --reporter=line`. Проверен `S-16-TC-008`: два короба в одной приёмке, короб A полностью разложен, короб B оставлен в сортировке; в каталоге виден текст `Товар из короба уже разложен`.
- Зелёный: из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup` выполнен `git diff --check`.

## Не реализовано

Нет. Реализован только атом 3 из `FEATURES.md`; проверки повтора списка, гонок сканирования и заголовка приёмки не менялись.

## Находки

Нет. Секреты, ключи, токены, `.env` и кабинеты учётных данных не открывались. Боевой сервер `194.87.96.144` не использовался.

# Фича 4

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
