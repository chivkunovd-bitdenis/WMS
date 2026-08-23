# 09-billing — screen-dev

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/screens/ff/FfBillingScreen.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/night/volna-9-recovery/cards/09-billing/DEV.md`

Экран использует закрытые словари отображаемых услуг и единиц: неизвестные значения API показываются как «—». Для начислений (в обоих режимах) и строк открытого счёта выводится `ErrorNotice`; технические коды не передаются в видимый интерфейс или печатную форму. Дополнительно устранены ошибки типизации в том же экране, не меняющие видимое поведение: отдельная типизация таблиц режимов и корректные MUI-свойства.

## Гейты

- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend && npx tsc --noEmit -p tsconfig.app.json` — красный из-за файлов вне границ атома: `FfSettingsScreen.tsx`, `SellersScreen.tsx`, `ui-kit/PeriodPicker.tsx`. Ошибок в `FfBillingScreen.tsx` после исправления нет.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing && python3 scripts/ui/ui_guard.py` — красный из-за ранее существующих новых нарушений вне границ атома: `WbProductPickerDialog.tsx`, `FfSettingsScreen.tsx`, `FfFbsSupplyWorkspace.tsx`, `SellerInboundDraftScreen.tsx`. Базовая линия не менялась.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend && npm run test:unit -- src/screens/ff/FfBillingScreen.test.ts` — зелёный: 1 файл, 4 теста.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend && npm run test:e2e -- tests-e2e/billing-ledger.spec.ts --grep "hides unknown service and unit codes in both modes"` — не стартовал: sandbox запретил привязку web-server к `127.0.0.1:18000` (`operation not permitted`).
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend && npm run test:e2e -- tests-e2e/billing-invoices.spec.ts --grep "hides unknown service and unit codes"` — не стартовал по той же причине до выполнения сценария.

## Не реализовано

- Ничего в пределах атома 6 не оставлено. Точечные E2E-сценарии присутствуют в разрешённых файлах, но среда не разрешает поднять их локальный сервер.

## Находки

- Секреты, ключи, токены, `.env` и кабинеты учётных данных не открывались.
- Изменения не удалось сохранить отдельным Git-коммитом: Git не может создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-3-09-billing1/index.lock` из-за запрета среды (`operation not permitted`). Рабочее дерево содержит изменения экрана и этот артефакт; чужой `night/volna-9-recovery/JOURNAL.md` не добавлялся.
