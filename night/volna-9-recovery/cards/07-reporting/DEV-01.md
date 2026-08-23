# DEV · 07-reporting · атом 1

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/deploy/Caddyfile.seller.local` — самостоятельный seller-Caddy обслуживает SPA только в канонической базе `/app/seller`, сохраняет доступ к ресурсам бандла и постоянным перенаправлением переносит корень и старые глубокие ссылки в эту базу.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/night/volna-9-recovery/cards/07-reporting/DEV.md` — отчёт этого шага.

## Гейты

- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend && npx tsc --noEmit -p tsconfig.app.json` — зелёный, exit 0.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting && python3 scripts/ui/ui_guard.py` — красный, exit 1: новые нарушения указаны только в не относящихся к атому файлах `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/App.tsx`, `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/components/WbProductPickerDialog.tsx`, `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx` и `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/screens/v2/SellerInboundDraftScreen.tsx`. Базовая линия не менялась.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend && npm run test:unit -- src/apps/seller/SellerApp.test.tsx` — зелёный, 2 passed.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend && VITE_SELLER_ROUTER_BASENAME=/app/seller npm run build` — зелёный, seller production bundle собран.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting && docker build --file frontend/Dockerfile.seller.prod --tag wms-seller-routing-07:local .` — не выполнен: Docker daemon недоступен (`permission denied` на `/Users/deniscivkunov/.docker/run/docker.sock`). Поэтому запросы `/`, `/documents` и `/app/seller/reports` через Caddy в контейнере этой средой не проверены.

## Не реализовано

- Живую проверку seller-образа через Caddy для `/`, `/documents` и `/app/seller/reports` нельзя выполнить без доступа к Docker daemon. Конфигурация этих путей реализована; production-сборка seller-бандла с basename `/app/seller` прошла.
- E2E-конфигурация из второй находки `REVIEW.md` не менялась: она относится к следующему атому `FEATURES.md` и запрещена рамками текущего шага.

## Находки

- Секреты, ключи, токены, `.env` и кабинеты учётных данных не читались и не изменялись.
- Git-индекс этого зарегистрированного worktree недоступен на запись: `git add` не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-1-07-reporting1/index.lock`. Поэтому изменения остаются локальными и не могут быть сохранены отдельным commit в этой среде.
