# 09-billing — screen-dev, атом 11

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/screens/ff/FfBillingScreen.tsx` — для списка счетов выбран последний закрытый месяц, календарный период показан в читаемом виде, а детализация хранения не показывает технический источник.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/tests-e2e/billing-invoices.spec.ts` — `S-31-TC-007` дополнительно проверяет снимки обеих сторон в HTML-печати и отсутствие управляющих кнопок.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/night/volna-9-recovery/cards/09-billing/DEV.md` — обязательный артефакт этапа.

## Гейты

- Зелёный: `npx --no-install tsc --noEmit -p tsconfig.app.json` (запуск из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend`).
- Красный, внешние для атома новые нарушения: `python3 ../scripts/ui/ui_guard.py` (запуск из `frontend/`) сообщает `src/App.tsx`, `src/components/WbProductPickerDialog.tsx`, `src/screens/ff/FfSettingsScreen.tsx`, `src/screens/v2/FfFbsSupplyWorkspace.tsx`, `src/screens/v2/SellerInboundDraftScreen.tsx`. Базовая линия не менялась.
- Красный: `npm run test:unit -- --run src/screens/ff/FfBillingScreen.test.tsx` — в рабочей копии отсутствует `vitest` (`sh: vitest: command not found`); отдельного unit-теста экрана в `src/screens/ff/` нет.
- Зелёный: `npx --no-install playwright test tests-e2e/billing-invoices.spec.ts` (запуск из `frontend/`), только назначенный e2e-файл атома.
- Зелёный: `git diff --check`.

## Не реализовано

- Пункты контракта атома 11, относящиеся к экрану и e2e `S-31-TC-007`/`S-31-TC-008`, реализованы.
- Находки REVIEW.md по API, сервисам, моделям, миграции, записи ledger и документу `docs/blockers/S-31.md` не относятся к разрешённым файлам фронтенд-экрана и e2e этого атома, поэтому не менялись.
