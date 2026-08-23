## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/screens/ff/FfBillingScreen.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/screens/ff/FfSettingsScreen.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/screens/ff/FfSettingsScreen.test.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/tests-e2e/billing-invoices.spec.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/night/volna-9-recovery/cards/09-billing/DEV.md`

Атом 16 направляет оба действия «Открыть тарифы» на
`/app/ff/settings?tab=tariffs`. Экран настроек читает параметр при открытии и
активирует «Тарифы ФФ»; обычный маршрут `/app/ff/settings` сохраняет штатную
вкладку «Склад и сотрудники».

## Гейты

- Зелёный: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend && npx tsc --noEmit -p tsconfig.app.json`.
- Красный вне границ атома: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing && python3 scripts/ui/ui_guard.py`. Сторож сообщает уже существующие превышения базовой линии: `FfSettingsScreen.tsx` 701 → 803 строк, а также `WbProductPickerDialog.tsx`, `FfFbsSupplyWorkspace.tsx` и `SellerInboundDraftScreen.tsx`. Базовая линия не изменялась.
- Зелёный: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend && npm run test:unit -- src/screens/ff/FfBillingScreen.test.ts src/screens/ff/FfSettingsScreen.test.ts` — 2 файла, 8 тестов passed.
- Не запущен по ограничению среды: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend && npx playwright test tests-e2e/billing-invoices.spec.ts --grep "tariff issue opens|charge tariff issue"`. Playwright webServer не смог привязаться к `127.0.0.1:18000`: `operation not permitted`.

## Не реализовано

Нет: оба действия «Открыть тарифы» реализованы буквально. E2E-проверка не выполнилась только из-за запрета окружения на локальный порт.

## Находки

- Для зелёного `ui_guard.py` требуется отдельная работа по сокращению уже увеличенных экранов; она выходит за пределы атома 16 и разрешённого списка файлов.
- Git-сохранение не выполнено: `git add`/`git commit` не могут создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-3-09-billing1/index.lock` из-за `Operation not permitted`. Изменения остаются в этой рабочей копии незакоммиченными.
