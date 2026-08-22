## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/screens/ff/FfBillingScreen.tsx` — реализована вкладка «Начисления»: период, селлер, услуга, поиск документа, режимы «По операциям»/«По исполнителям», таблица через `DataTable`, проблема «Нет тарифа», пустое/загрузочное/ошибочное состояния и сохранение контекста вкладок.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/tests-e2e/billing-ledger.spec.ts` — добавлены сценарии `S-31-TC-004`, `S-31-TC-005`, `S-31-TC-012` с мокированием чтения журнала.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — PASS.
- `python3 scripts/ui/ui_guard.py` — FAIL: храповик показывает пять ранее существовавших нарушений в `src/App.tsx`, `src/components/WbProductPickerDialog.tsx`, `src/screens/ff/FfSettingsScreen.tsx`, `src/screens/v2/FfFbsSupplyWorkspace.tsx`, `src/screens/v2/SellerInboundDraftScreen.tsx`; изменённый экран billing в списке новых нарушений отсутствует. Базовую линию не обновлял.
- `npm run test:unit` — FAIL: в окружении отсутствует исполняемый `vitest` (`vitest: command not found`).

## Не реализовано

- Вкладка «Счета» и детализация счёта не расширялись: этот атомарный кусок FEATURES.md ограничен реестром начислений.
- В текущем checkout нет GET-ручки журнала в `backend/app/api/billing.py`; экран вызывает согласованный ресурс `/api/billing/ledger`, а E2E покрывает пользовательский результат через маршрутный mock. Добавление backend-файла запрещено списком файлов этой карточки.
- Секреты, ключи, токены, `.env`, кабинеты учётных данных и боевой прод не читались и не затрагивались.
