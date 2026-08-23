# 09-billing — атом 13: честное сторно по исполнителям

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/screens/ff/FfBillingScreen.tsx` — распознаёт `entry_type`; режим «По исполнителям» не суммирует строки `reversal`, а строка операции сторно явно подписана «Сторно» и по уже переданной API ссылке открывает исходный документ.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/tests-e2e/billing-ledger.spec.ts` — добавлен `S-31-TC-016`: начисление Анны и сторно Бориса, отсутствие Бориса и −20 в итогах исполнителей, затем переход из помеченного сторно к исходной приёмке.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/night/volna-9-recovery/cards/09-billing/DEV.md` — отчёт по атому.

## Гейты

- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend && npx tsc --noEmit -p tsconfig.app.json` — зелёный, код 0.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing && python3 scripts/ui/ui_guard.py` — красный, код 1. Новые отступления перечислены только вне атома: `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/components/WbProductPickerDialog.tsx`, `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/screens/ff/FfSettingsScreen.tsx`, `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx`, `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/screens/v2/SellerInboundDraftScreen.tsx`. Базовая линия не обновлялась.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend && npm run test:unit -- src/screens/ff/FfBillingScreen.test.ts` — зелёный: 1 файл, 4 теста.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend && npx playwright test tests-e2e/billing-ledger.spec.ts --grep 'excludes reversals from performer totals' --list` — зелёный: обнаружен 1 адресный сценарий.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend && npx playwright test tests-e2e/billing-ledger.spec.ts --grep 'excludes reversals from performer totals'` — не выполнен: Playwright webServer не смог открыть `127.0.0.1:18000` (`operation not permitted`) до запуска сценария.

## Не реализовано

Нет. API-признак `entry_type` и ссылка сторно на исходный документ уже поставлены атомом 9; этот атом реализует их отображение строго в разрешённых фронтенд-файлах.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных и боевой прод не читались и не затрагивались.
- Git-сохранение не выполнено: `git add frontend/src/screens/ff/FfBillingScreen.tsx frontend/tests-e2e/billing-ledger.spec.ts night/volna-9-recovery/cards/09-billing/DEV.md` не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-3-09-billing1/index.lock` (`Operation not permitted`). Изменения остаются локально в этой рабочей копии без commit SHA.
