# 09-billing — screen-dev, повторный ремонт атома 9

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/screens/ff/FfBillingScreen.tsx` — номер приёмки или MP-отгрузки в журнале начислений стал ссылкой на существующий документ; технические источники без доступного документа остаются обычным текстом.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/App.tsx` — штатный callback открытия приёмки передан экрану расчётов; billing-маршрут уплотнён, поэтому размер монолита по `ui_guard` уменьшился с базовых 3492 до 3491 строки.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/screens/ff/FfBillingScreen.test.ts` — добавлена адресная проверка маршрутов исходных документов.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/tests-e2e/billing-ledger.spec.ts` — сценарий `S-31-TC-004` дополнен кликом по номеру приёмки и проверкой открытия штатного диалога документа с сохранением маршрута `/app/ff/billing`.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/night/volna-9-recovery/cards/09-billing/DEV.md` — этот отчёт.

## Гейты

- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend && npm_config_offline=true npx tsc --noEmit -p tsconfig.app.json` — **красный до запуска TypeScript**: в рабочей копии отсутствует `frontend/node_modules`, а локального кэшированного пакета `tsc` нет (`ENOTCACHED`). Сеть и другой checkout не использовались.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing && python3 scripts/ui/ui_guard.py` — **красный в целом, но зелёный для файлов атома**: `src/App.tsx` стало лучше, `3492 → 3491`; новых нарушений в `FfBillingScreen.tsx` нет. Остались четыре ранее существующих нарушения вне разрешённого слоя: `src/components/WbProductPickerDialog.tsx`, `src/screens/ff/FfSettingsScreen.tsx`, `src/screens/v2/FfFbsSupplyWorkspace.tsx`, `src/screens/v2/SellerInboundDraftScreen.tsx`. Базовая линия не менялась.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend && npm run test:unit -- src/screens/ff/FfBillingScreen.test.ts` — **красный до запуска тестов**: `vitest: command not found`, потому что `frontend/node_modules` отсутствует.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend && npm_config_offline=true npx playwright test tests-e2e/billing-ledger.spec.ts -g "billing ledger preserves filters and month context"` — **красный до запуска сценария**: пакет Playwright отсутствует в локальном npm-кэше (`ENOTCACHED`).
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing && git diff --check` — **зелёный**.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing && git add -- frontend/src/App.tsx frontend/src/screens/ff/FfBillingScreen.tsx frontend/src/screens/ff/FfBillingScreen.test.ts frontend/tests-e2e/billing-ledger.spec.ts night/volna-9-recovery/cards/09-billing/DEV.md && git diff --cached --check && git status --short && git commit -m 'night(09-billing): open ledger source documents'` — **красный до индексации**: Git не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-3-09-billing1/index.lock` (`Operation not permitted`). Несвязанные `JOURNAL.md` и `REVIEW.md` не индексировались.

## Не реализовано

- В разрешённых файлах экрана находка 1 из `REVIEW.md` реализована буквально для двух production-источников, у которых существуют пользовательские документы: `inbound_intake` и `marketplace_unload`.
- Находки 2 и 3 из `REVIEW.md` относятся к backend-сервису и backend-тесту. По заданной роли `screen-dev` и границам этого атома они не изменялись.
- Для `storage_measurement` и `billing_reversal` ссылка не рисуется: текущий read-model не отдаёт доступный пользовательский маршрут исходного документа для этих типов. Технический UUID пользователю не показывается.
- Изменения локально реализованы, но не сохранены в новом Git-коммите: служебный каталог зарегистрированного worktree недоступен для записи, поэтому восстанавливаемого SHA у этого ремонта нет.

## Находки

- Локальные npm-зависимости отсутствуют, поэтому `tsc`, Vitest и адресный Playwright-кейс необходимо повторить после штатной установки зависимостей интеграционным шагом.
- Секреты, ключи, токены, `.env`, кабинеты учётных данных, живой Wildberries и боевой прод не читались и не затрагивались.
