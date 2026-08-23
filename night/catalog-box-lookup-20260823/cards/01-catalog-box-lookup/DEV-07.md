# Screen-dev · 01-catalog-box-lookup · атом 7

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/frontend/src/screens/v2/FfCatalogInboundPackages.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/night/catalog-box-lookup-20260823/cards/01-catalog-box-lookup/DEV.md`

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` (из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/frontend`) — не завершён: в рабочей копии отсутствует `frontend/node_modules/.bin/tsc`; `npx` ожидал загрузку пакета из сети и был остановлен после 60 секунд без вывода.
- `python3 scripts/ui/ui_guard.py` (из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup`) — красный по существующим отступлениям в `src/components/WbProductPickerDialog.tsx`, `src/screens/v2/FfFbsSupplyWorkspace.tsx`, `src/screens/v2/FfProductsCatalogScreen.tsx` и `src/screens/v2/SellerInboundDraftScreen.tsx`. Этот атом не меняет ни один из них и базовая линия не обновлялась.
- `npm run test:unit -- --run frontend/src/screens/v2/FfCatalogInboundPackages.test.tsx` (из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/frontend`) — не выполнен: `sh: vitest: command not found`. Отдельного unit-теста этого атома в контракте и реестре нет; следующий атом 8 владеет e2e-файлом.
- `git diff --check` (из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup`) — зелёный.

## Не реализовано

Нет. Если `request_display_number` уже содержит `№`, заголовок показывает номер без второго префикса; fallback на `request_id` добавляет ровно один `№`.

## Находки

Секреты, ключи, токены, `.env` и кабинеты учётных данных не читались. Локальные зависимости frontend отсутствуют, поэтому TypeScript и Vitest в этой рабочей копии не были выполнены.
