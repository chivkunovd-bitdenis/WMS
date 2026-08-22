## Изменённые файлы

- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/screens/ff/FfBillingScreen.tsx — добавлен вывод блокирующих причин выпуска счёта с единственным исправляющим действием; раскрытие детализации показывает исходные документы отдельными строками.
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/tests-e2e/billing-invoices.spec.ts — существующие сценарии S-31-TC-007 и S-31-TC-008 проверены; изменений тестового файла не потребовалось.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — зелёный.
- `python3 scripts/ui/ui_guard.py` — красный из-за пяти уже существующих нарушений в несвязанных файлах: `src/App.tsx`, `src/components/WbProductPickerDialog.tsx`, `src/screens/ff/FfSettingsScreen.tsx`, `src/screens/v2/FfFbsSupplyWorkspace.tsx`, `src/screens/v2/SellerInboundDraftScreen.tsx`. Базовую линию не обновлял.
- `npm run test:unit` — не запустился: в рабочей копии отсутствует команда `vitest` (`vitest: command not found`).

## Не реализовано

- REVIEW находки по backend API, автоматическому выставлению, моделям и сервисам не менялись: контракт этого атома разрешает только экран `FfBillingScreen.tsx` и `billing-invoices.spec.ts`.
- Кнопки исправления блокирующих причин оставлены без навигации, поскольку контракт не указывает маршруты для тарифов, селлера и хранения, а соседние экраны запрещены к изменению.
- E2E-сценарии S-31-TC-007 и S-31-TC-008 не запускались отдельно: в рабочей копии отсутствуют зависимости frontend для unit-запуска, а обязательный `ui_guard.py` уже сообщает несвязанные нарушения.
