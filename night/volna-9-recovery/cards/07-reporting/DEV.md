# Фича 1

# DEV · 07-reporting · атом 1

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/deploy/Caddyfile.seller`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/Dockerfile.seller.prod`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/night/volna-9-recovery/cards/07-reporting/DEV.md`

## Гейты

- `git diff --check` — зелёный.
- `docker build -f frontend/Dockerfile.seller.prod -t wms-seller-reporting-07:local .` — не выполнен: среда запретила подключение к локальному Docker socket (`permission denied` для `/Users/deniscivkunov/.docker/run/docker.sock`). Поэтому контейнерные проверки постоянных редиректов `/` и `/documents`, а также seller-bundle по `/app/seller/reports`, не подтверждены в этой среде.
- `npx tsc --noEmit -p tsconfig.app.json` (из `frontend/`) — зелёный.
- `python3 scripts/ui/ui_guard.py` (из корня) — красный из-за новых нарушений в не относящихся к атому файлах: `frontend/src/App.tsx`, `frontend/src/components/WbProductPickerDialog.tsx`, `frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx`, `frontend/src/screens/v2/SellerInboundDraftScreen.tsx`. Базовая линия не менялась, эти файлы не трогались, так как они за границей атома.
- `npm run test:unit` (из `frontend/`) — зелёный: 24 test files, 148 tests.
- `npx vitest run src/apps/seller/SellerApp.test.tsx` (из `frontend/`) — зелёный: 1 test file, 2 tests. Это точечная seller-регрессия из вердикта.
- `VITE_SELLER_ROUTER_BASENAME=/app/seller npm run build` (из `frontend/`) — зелёный: production bundle содержит `dist/seller/index.html` и seller entrypoint.

## Не реализовано

- Контейнерная проверка из условия атома не выполнена буквально: доступ к Docker daemon запрещён средой. Сам production Dockerfile теперь берёт отслеживаемый Git-файл `frontend/deploy/Caddyfile.seller`; Caddyfile содержит постоянный редирект legacy-путей в `/app/seller{uri}` и отдачу seller bundle только на `/app/seller` и `/app/seller/*`.
- Находка REVIEW о `E2E_SELLER_PATH_PREFIX` не исправлялась: это самостоятельный атом 2 в `FEATURES.md`, а текущий запуск ограничен атомом 1.
- Отдельный Git commit не создан: Git запрещает создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-1-07-reporting1/index.lock` (`Operation not permitted`).

## Находки

- Секреты, ключи, токены, `.env` и кабинеты учётных данных не читались и не изменялись.

# Фича 2

# DEV · 07-reporting · feature 2

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/playwright.config.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/tests-e2e/inbound-boxes-helpers.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/night/volna-9-recovery/cards/07-reporting/DEV.md`

## Гейты

- ЗЕЛЁНЫЙ — `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend && npx tsc --noEmit -p tsconfig.app.json`.
- КРАСНЫЙ, не относится к этому атому — `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting && python3 scripts/ui/ui_guard.py`. Скрипт обнаружил новые отклонения в чужих файлах: `frontend/src/App.tsx`, `frontend/src/components/WbProductPickerDialog.tsx`, `frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx`, `frontend/src/screens/v2/SellerInboundDraftScreen.tsx`. Они вне разрешённых файлов атома и не изменялись в этой работе; базовую линию не обновлял.
- ЗЕЛЁНЫЙ — `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend && npm run test:unit -- src/apps/seller/SellerApp.test.tsx`: 2 теста прошли.
- КРАСНЫЙ по ограничению среды — `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend && npm run test:e2e -- seller-reports.spec.ts`. Playwright запустил API, но среда запретила bind `127.0.0.1:18000` (`[Errno 1] operation not permitted`), поэтому адресный сценарий не начал выполняться.
- КРАСНЫЙ по ограничению среды — `git add frontend/playwright.config.ts frontend/tests-e2e/inbound-boxes-helpers.ts night/volna-9-recovery/cards/07-reporting/DEV.md && git commit -m "test(seller): share production route prefix with e2e workers"`. Git не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-1-07-reporting1/index.lock` (`Operation not permitted`), поэтому изменения нельзя восстановить из commit SHA до снятия ограничения на метаданные worktree.

## Не реализовано

- Нет в коде. Production-префикс `/app/seller` установлен единым значением в Playwright-конфигурации, передаётся Vite и публикуется в окружение воркеров; helper использует тот же production-дефолт. Выполнение браузерного сценария не удалось подтвердить только из-за запрета среды на локальный порт, а сохранение изменений коммитом — из-за запрета записи в метаданные worktree.

## Находки

- В текущем рабочем дереве присутствует несвязанное изменение `night/volna-9-recovery/JOURNAL.md`; оно не включено в эту работу.
