# DEV · 07-reporting · атом 2

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/playwright.config.ts` — e2e Vite получает production basename `/app/seller`, seller-путь и URL портала на том же origin.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/vite.config.ts` — SPA fallback seller-бандла использует `VITE_SELLER_ROUTER_BASENAME`, включая корневой URL указанной базы.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/tests-e2e/seller-reports.spec.ts` — прямой сценарий берёт путь через seller-конфигурацию и явно закрепляет канонический `/app/seller/reports`.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/night/volna-9-recovery/cards/07-reporting/DEV.md` — отчёт атома.

## Гейты

- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend && npx tsc --noEmit -p tsconfig.app.json` — зелёный, exit 0.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend && python3 ../scripts/ui/ui_guard.py` — красный, exit 1. Новых нарушений в файлах атома нет; guard сообщает только ранее существовавшие чужие экраны: `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/App.tsx`, `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/components/WbProductPickerDialog.tsx`, `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx`, `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/screens/v2/SellerInboundDraftScreen.tsx`. Базовая линия не менялась.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend && npm run test:unit -- src/apps/seller/SellerApp.test.tsx` — зелёный, 1 файл и 2 теста passed.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend && VITE_SELLER_ROUTER_BASENAME=/app/seller npm run build` — зелёный; собраны seller и FF entrypoints с production basename.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend && npx playwright test tests-e2e/seller-reports.spec.ts --grep 'seller staff without products access cannot open the direct reports route' --list` — зелёный, найден ровно один адресный сценарий.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend && npx playwright test tests-e2e/seller-reports.spec.ts --grep 'seller staff without products access cannot open the direct reports route'` — не стартовал: среда запретила bind backend на `127.0.0.1:18000` (`[Errno 1] operation not permitted`) до выполнения браузерного теста.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting && docker build --file frontend/Dockerfile.seller.prod --tag wms-seller-routing-07:local .` — не стартовал: Docker daemon недоступен (`permission denied` для `/Users/deniscivkunov/.docker/run/docker.sock`). Поэтому живой Caddy-сценарий корня и старой ссылки из атома 1 в этой среде не выполнен.

## Не реализовано

- Кодовые пункты атома реализованы буквально. Живой Playwright-кейс не может быть завершён без разрешённого bind на loopback; это ограничение среды, а не изменённый сценарий.
- Живую проверку `/` и старой ссылки `/documents` через самостоятельный seller-Caddy нельзя выполнить без Docker daemon. Конфигурация атома 1 не менялась; production build с `/app/seller` прошёл.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных, боевой сервер и запись в Wildberries не читались и не затрагивались.
- Отдельный commit не создан: Git запретил создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-1-07-reporting1/index.lock` (`Operation not permitted`). Изменения остаются локальным diff этой зарегистрированной рабочей копии.
