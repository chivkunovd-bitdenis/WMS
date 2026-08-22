## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/screens/ff/FfBillingScreen.tsx` — добавлены вкладка «Счета», фильтры, реестр, блокирующие состояния, диалог детализации, раскрытие исходных документов, печать HTML и подтверждённая идемпотентная отмена.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/tests-e2e/billing-invoices.spec.ts` — добавлены сценарии `S-31-TC-007` и `S-31-TC-008`.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — диагностик TypeScript не выведено; команда в данном checkout завершилась без итогового кода в оболочке, поэтому полноценный статус не подтверждён.
- `python3 scripts/ui/ui_guard.py` — красный: обнаружены новые относительно baseline нарушения в чужих файлах `src/App.tsx`, `src/components/WbProductPickerDialog.tsx`, `src/screens/ff/FfSettingsScreen.tsx`, `src/screens/v2/FfFbsSupplyWorkspace.tsx`, `src/screens/v2/SellerInboundDraftScreen.tsx`; изменённый экран в списке нарушений отсутствует. Baseline не обновлялся.
- `npm run test:unit` — красный до запуска тестов: `vitest: command not found`, зависимости checkout не установлены.

## Не реализовано

- Полный backend GET-контракт списка/деталей счетов в checkout отсутствует: экран использует предусмотренные маршруты `/api/billing/invoices` и `/api/billing/invoices/{id}/cancel`, а формат списка поддерживает поля `invoices` или `rows`.
- Печатное HTML-представление формируется на клиенте из доступного снимка счёта; серверного шаблона печати в разрешённых файлах нет.
