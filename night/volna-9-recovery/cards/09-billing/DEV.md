## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/screens/ff/FfBillingScreen.tsx` — исправлено состояние повторного формирования счёта: блокирующая причина передаётся через `disabledReason`, после устранения причин показывается действие с контрактной подписью; переходы «Открыть тарифы» и другие исправляющие действия сохранены.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/tests-e2e/billing-ledger.spec.ts` — сценарий `S-31-TC-004` теперь проверяет отправку номера документа в запросе, а также сохранение данных при переключении вкладок.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — не подтверждён: локальная команда `npx` не завершилась и не вывела результат; остановлена после ожидания.
- `python3 scripts/ui/ui_guard.py` — красный по пяти нарушениям в несвязанных файлах: `frontend/src/App.tsx`, `frontend/src/components/WbProductPickerDialog.tsx`, `frontend/src/screens/ff/FfSettingsScreen.tsx`, `frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx`, `frontend/src/screens/v2/SellerInboundDraftScreen.tsx`. Базовая линия не изменялась.
- `npm run test:unit` — не запущен: в окружении отсутствует исполняемый файл `vitest` (`vitest: command not found`).

## Не реализовано

- Backend-находки ревью (GET API, пересчёт начислений, timezone, идемпотентность и миграции) не изменялись: контракт этого атома разрешает только экран `FfBillingScreen.tsx` и `billing-ledger.spec.ts`.
- Исправление доступа и состояния вкладки тарифов в `FfSettingsScreen.tsx` не выполнялось по той же границе файлов.
