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
