# 09-billing · screen-dev rework

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/screens/ff/FfBillingScreen.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/tests-e2e/billing-invoices.spec.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/night/volna-9-recovery/cards/09-billing/DEV.md`

Экран берёт блокирующие причины из отдельного поля `issues` ответа списка счетов, а не из несуществующего поля счёта. После успешного повторного формирования он повторно запрашивает список. Добавлен e2e-сценарий `S-31-TC-013` для видимой причины и исправляющего действия.

## Гейты

- Зелёный: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend && npx tsc --noEmit -p tsconfig.app.json`.
- Красный, новых нарушений экран не добавил: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing && python3 scripts/ui/ui_guard.py`. Зафиксированы уже существующие нарушения в `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/App.tsx`, `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/components/WbProductPickerDialog.tsx`, `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/screens/ff/FfSettingsScreen.tsx`, `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx` и `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/screens/v2/SellerInboundDraftScreen.tsx`; `--update` не применялся.
- Красный из-за неполных локальных зависимостей: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend && npm run test:unit -- --passWithNoTests FfBillingScreen` → `vitest: command not found`.
- Красный из-за тех же неполных зависимостей: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend && npm run test:e2e -- billing-ledger.spec.ts billing-invoices.spec.ts` → `error: unknown command 'test'`; локального `node_modules/.bin/playwright` нет.
- Зелёный: `git diff --check`.

## Не реализовано

- Backend-находки из `REVIEW.md` не изменялись: роль `screen-dev` ограничена экранным слоем.
- Целевые unit/e2e не запущены до завершения из-за отсутствующих локальных зависимостей. В тестовом файле добавлен сценарий, но его выполнение требует восстановить зависимости этой рабочей копии.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных и боевой прод не открывались и не затрагивались.
