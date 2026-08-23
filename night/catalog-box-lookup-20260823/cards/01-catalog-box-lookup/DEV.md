# Реализация · 01-catalog-box-lookup · атом 1

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/frontend/tests-e2e/catalog-box-lookup.spec.ts` — перед посимвольным вводом `INB-NEXT-SCAN` тест явно выделяет старый внутренний ШК и проверяет границы выделения.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/night/catalog-box-lookup-20260823/cards/01-catalog-box-lookup/DEV.md` — обязательный артефакт реализации.

## Гейты

- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/frontend && npx playwright test tests-e2e/catalog-box-lookup.spec.ts -g 'catalog deduplicates repeated scans while the first lookup is pending'` — красный: локальный Playwright отсутствует; `npx` попытался загрузить пакет, но сеть недоступна (`ENOTFOUND registry.npmjs.org`).
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/frontend && npx tsc --noEmit -p tsconfig.app.json` — красный: локальный `tsc` отсутствует; `npx` не смог загрузить пакет из-за недоступной сети (`ENOTFOUND registry.npmjs.org`).
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup && python3 scripts/ui/ui_guard.py` — красный: новые нарушения обнаружены только в неразрешённых этим атомом файлах `src/components/WbProductPickerDialog.tsx`, `src/screens/v2/FfFbsSupplyWorkspace.tsx`, `src/screens/v2/FfProductsCatalogScreen.tsx`, `src/screens/v2/SellerInboundDraftScreen.tsx`; базовая линия не менялась.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/frontend && npm run test:unit` — красный: локальный `vitest` отсутствует (`sh: vitest: command not found`).
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup && git diff --check -- frontend/tests-e2e/catalog-box-lookup.spec.ts` — зелёный.

## Не реализовано

Все требования атома в указанном тесте реализованы буквально. Запуск целевого Playwright-сценария и обязательных frontend-гейтов не подтверждён из-за отсутствующих локальных зависимостей и недоступной сети; отклонения `ui_guard.py` относятся к четырём файлам вне разрешённого слоя атома и поэтому не исправлялись.
