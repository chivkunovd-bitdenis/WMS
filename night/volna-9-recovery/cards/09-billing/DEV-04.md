# 09-billing — DEV

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/screens/ff/FfBillingScreen.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/screens/ff/FfBillingScreen.test.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/tests-e2e/billing-invoices.spec.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/night/volna-9-recovery/cards/09-billing/DEV.md`

## Гейты

- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend && npm run test:unit -- src/screens/ff/FfBillingScreen.test.ts` — зелёный: 1 файл, 8 тестов.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend && npx tsc --noEmit -p tsconfig.app.json` — зелёный.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing && python3 scripts/ui/ui_guard.py` — красный только из-за не относящихся к атому файлов: `frontend/src/components/WbProductPickerDialog.tsx`, `frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx`, `frontend/src/screens/v2/SellerInboundDraftScreen.tsx`. Базовая линия не менялась, эти файлы не правились.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend && npm run test:e2e -- billing-invoices.spec.ts` — не запустился: окружение запретило bind `127.0.0.1:18000` (`operation not permitted`) на этапе `webServer`, тестовые утверждения не выполнялись.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing && git diff --check` — зелёный.

## Не реализовано

- Все пункты контракта атома 4 реализованы: экран, детализация и печатный HTML передают копейки в единый форматтер без повторного деления; E2E-фикстуры используют значения API `1200`, `1494000`, `8`, `1455200` и добавлена проверка `63000 → 630,00 ₽` в таблице начислений.
- Целевой Playwright не выполнен из-за запрета окружения на запуск локального веб-сервера. Повторный запуск нужен там, где разрешён bind порта.

## Находки

- Секреты, ключи, токены, `.env` и кабинеты учётных данных не читались и не затрагивались.
