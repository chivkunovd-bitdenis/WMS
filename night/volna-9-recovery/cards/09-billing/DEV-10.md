## Изменённые файлы

- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/screens/ff/FfBillingScreen.tsx
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/tests-e2e/billing-ledger.spec.ts
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/night/volna-9-recovery/cards/09-billing/DEV.md

## Гейты

- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend && npx tsc --noEmit -p tsconfig.app.json` — зелёный.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend && npx playwright test tests-e2e/billing-ledger.spec.ts` — зелёный; выполнен только тестовый файл атома.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend && npm run test:unit -- --runInBand` — красный до запуска тестов: `sh: vitest: command not found`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing && python3 scripts/ui/ui_guard.py` — красный из-за уже имеющихся отклонений вне файлов атома: `src/App.tsx`, `src/components/WbProductPickerDialog.tsx`, `src/screens/ff/FfSettingsScreen.tsx`, `src/screens/v2/FfFbsSupplyWorkspace.tsx`, `src/screens/v2/SellerInboundDraftScreen.tsx`. Базовая линия не обновлялась.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing && git diff --check` — зелёный.
- Сохранение отдельным Git-коммитом не выполнено: Git не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-3-09-billing1/index.lock` из-за ограничения прав текущей среды. Чужой `night/volna-9-recovery/JOURNAL.md` в индекс не добавлялся.

## Не реализовано

- Для S-31-TC-004, S-31-TC-005 и S-31-TC-012 экран передаёт в живой ledger API начало выбранного месяца в `date=YYYY-MM-01`, не отправляет `seller_id=all` и принимает реальный массив строк. Поиск, фильтр услуги и данные полей строки требуют серверного read-model; это находка ревью №2 и находится за границей screen-dev.
- Находки ревью №3–12 и №14 относятся к API, сервисам, миграциям и документации блокировок, поэтому в этот атомарный экранный проход не вносились. Находка №13 про `billing-invoices.spec.ts` также не относится к разрешённому тестовому файлу атома.
- Контракт не удалось подтвердить полностью: `test:unit` не запускается из-за отсутствующего Vitest, а `ui_guard.py` блокируется нарушениями в чужих файлах.
