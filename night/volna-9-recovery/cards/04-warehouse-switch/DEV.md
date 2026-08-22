# DEV · 04-warehouse-switch · атом 10

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/FfFbsSupplyWorkspace.test.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/tests-e2e/ff-fbs-supply.spec.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/night/volna-9-recovery/cards/04-warehouse-switch/DEV.md`

В рабочем месте FBS ключ идемпотентности теперь хранится вместе с `order_id`: сетевой повтор незавершённого подбора использует ту же пару, а следующая физическая единица одинакового SKU выбирает следующий неподобранный заказ и получает новый ключ. Скан ячейки другого склада меняет только место фактического подбора и больше не подменяет показанный склад консолидации документа. Существующая реализация `FfFbsOrdersScreen.tsx` проверена: при нуле операционных складов она уже возвращает `EmptyState` «Нет рабочего склада», а строки без выбранного склада не показывает.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend` — **красный вне файлов атома**. TypeScript не находит уже используемый соседним `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/ui-kit/WarehouseContextSwitch.test.tsx` пакет `@testing-library/react` и его DOM-матчеры. Ошибок в трёх изменённых frontend-файлах команда не показала.
- `python3 scripts/ui/ui_guard.py` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch` — **красный на накопленном diff ветки**: guard считает новыми монолиты `WbProductPickerDialog.tsx`, `FfFbsOrdersScreen.tsx`, `FfFbsStockSyncScreen.tsx`, `FfFbsSupplyWorkspace.tsx` и `SellerInboundDraftScreen.tsx`. Baseline флагом `--update` не менялась.
- `npm run test:unit` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend` — **зелёный**: 22 файла, 156 тестов. Новый `TC-S17-007` подтверждает отдельные ключи для двух одинаковых SKU и повтор последней незавершённой операции тем же ключом.
- `npx playwright test tests-e2e/ff-fbs-supply.spec.ts --grep "scan location then product" --list` — **зелёный**, найден один целевой Chromium-сценарий.
- Живой запуск этого Playwright-сценария — **красный из-за ограничения среды до выполнения теста**: webServer не получил право открыть `127.0.0.1:18000` (`Errno 1 operation not permitted`).
- `git diff --check` — **зелёный**.
- Сохранение отдельным Git-коммитом — **заблокировано правами среды**: `git add` не может создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-1-04-warehouse-switch/index.lock` (`Operation not permitted`). Изменения остаются в рабочем дереве без нового commit SHA.

## Не реализовано

- Общий сессионный контекст из находки ревью № 4 не менялся: его полное исправление требует `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/App.tsx`, `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/contexts/WarehouseContext.tsx` и S-04, которые не входят в разрешённые файлы атома 10. В текущей ветке S-03 уже использует `useWarehouseContext('fulfillment')`, но сквозную согласованность всех экранов этот проход не заявляет.
- Полностью зелёные `tsc` и `ui_guard.py` не получены без выхода за границы атома: причины перечислены в разделе «Гейты».
- Живое прохождение E2E невозможно в этой песочнице из-за запрета bind локального порта; сам сценарий собран Playwright и включает два одинаковых SKU, сетевой повтор, кросс-складскую ячейку и неизменный склад документа.
- Публикация в Git не выполнена: общий Git-каталог зарегистрированного worktree доступен только для чтения. Временный клон и перенос в другую рабочую копию не использовались, поскольку роль требует оставаться в выданной копии.

## Находки

Секреты, ключи, токены, `.env`, кабинеты учётных данных и боевой прод `194.87.96.144` не открывались и не изменялись. Новых находок о данных или персональных данных в разрешённом слое нет.
