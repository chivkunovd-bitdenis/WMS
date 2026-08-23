# Screen-dev · 01-catalog-box-lookup · атом 6

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/frontend/src/screens/v2/FfCatalogInboundPackages.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/frontend/src/screens/v2/FfProductsCatalogScreen.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/frontend/tests-e2e/catalog-box-lookup.spec.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/night/catalog-box-lookup-20260823/cards/01-catalog-box-lookup/DEV.md`

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` (из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/frontend`) — не выполнен: локальный `tsc` отсутствует, а `npx` не смог загрузить пакет из-за `ENOTFOUND registry.npmjs.org`.
- `python3 scripts/ui/ui_guard.py` (из корня рабочей копии) — красный: храповик сообщает новые отступления в `src/components/WbProductPickerDialog.tsx`, `src/screens/v2/FfFbsSupplyWorkspace.tsx`, `src/screens/v2/FfProductsCatalogScreen.tsx` и `src/screens/v2/SellerInboundDraftScreen.tsx`. Базовая линия не изменялась. Для S-16 причина — уже существующий размер экрана; данный атом добавляет одну защитную строку.
- `npm run test:unit` (из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/frontend`) — не выполнен: `sh: vitest: command not found`.
- `npx playwright test tests-e2e/catalog-box-lookup.spec.ts --grep 'late failed scan'` (из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/frontend`) — не выполнен: локальный Playwright отсутствует, а `npx` не смог загрузить пакет из-за `ENOTFOUND registry.npmjs.org`.
- `git diff --check` — зелёный.
- Сохранение Git — не выполнено: `git add … && git commit -m "fix(catalog): ignore stale inbound scan responses"` не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-1-01-catalog-box-lookup/index.lock` (`Operation not permitted`). Поэтому проверенного commit SHA нет.

## Не реализовано

Нет. Поздний неуспешный lookup теперь возвращает `null`, если его номер запроса устарел; родитель не меняет ошибку, фокус или выделение для `null`. Добавлен сценарий S-16-TC-013/S-16-TC-016 с задержанным первым lookup, успешным вторым и начатым третьим вводом.

## Находки

Зависимости frontend не установлены в этой рабочей копии, а сеть до npm registry недоступна, поэтому TypeScript, Vitest и целевой Playwright-сценарий здесь не были исполнены. Секреты, ключи, токены, `.env` и кабинеты учётных данных не читались.
