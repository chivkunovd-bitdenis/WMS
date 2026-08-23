# DEV · 04-warehouse-switch · атом 1

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/FfFbsOrdersScreen.tsx` — реализация атома уже сохранена в commit `557ea2f5`: внешний дублирующий `Alert` отсутствует, а единственный `ErrorNotice` остаётся внутри `WarehouseContextSwitch` с `testId="fbs-wms-warehouse-context"`.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/tests-e2e/ff-fbs-supply.spec.ts` — в том же commit уже есть точечный сценарий ошибки: он проверяет один текст в контексте и отсутствие `fbs-wms-warehouse-context-error`.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/night/volna-9-recovery/cards/04-warehouse-switch/DEV.md` — восстановлен обязательный артефакт screen-dev после удаления из рабочего дерева.

## Гейты

- ЗЕЛЁНЫЙ: из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend` выполнено `npx tsc --noEmit -p tsconfig.app.json` (exit 0).
- КРАСНЫЙ: из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch` выполнено `python3 scripts/ui/ui_guard.py` (exit 1). Сторож фиксирует новые относительно своей baseline (базовой линии) экранные монолиты, в том числе `frontend/src/screens/v2/FfFbsOrdersScreen.tsx: 1587 → 1670`, а также четыре экрана вне атома. По правилу роли baseline флагом `--update` не менялся.
- ЗЕЛЁНЫЙ: из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend` выполнено `npm run test:unit -- src/ui-kit/WarehouseContextSwitch.test.ts src/ui-kit/WarehouseContextSwitch.runner.test.ts` (2 файла, 14 тестов, exit 0).
- НЕ ЗАПУЩЕНЫ СЦЕНАРИИ: из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend` выполнено `npx playwright test tests-e2e/ff-fbs-supply.spec.ts --grep 'WMS warehouse context is sent to the server|warehouse load error is shown once in the context'`. Локальный `webServer` не смог привязаться к `127.0.0.1:18000` (`operation not permitted`, exit 1), поэтому оба узко ограниченных browser-сценария не стартовали.

## Не реализовано

- По коду атом реализован буквально: при ошибке загрузки складов S-03 показывает ровно один `ErrorNotice` с текстом `Не удалось загрузить склады. Обновите страницу.` внутри `fbs-wms-warehouse-context`; внешнего `fbs-wms-warehouse-context-error` нет. Действия, зависящие от WMS-склада, остаются заблокированными существующим отсутствием выбранного склада.
- Невозможно подтвердить browser-выполнение в этой среде: она запрещает bind (привязку) локального порта `127.0.0.1:18000`. Код, TypeScript и относящиеся unit-регрессии проверены.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных и боевой прод `194.87.96.144` не открывались и не изменялись.

# Фича 2

# DEV · 04-warehouse-switch · атом 2

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/FfFbsStockSyncScreen.tsx` — подпись главного действия S-04 сокращена до `Выгрузить остатки`; условие включённых привязок и доступность кнопки не менялись.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/tests-e2e/ff-fbs-stock-sync.spec.ts` — сценарий S-04 теперь явно проверяет короткую подпись кнопки и её недоступность на складе без строк для выгрузки.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/night/volna-9-recovery/cards/04-warehouse-switch/DEV.md` — отчёт роли screen-dev для атома 2.

## Гейты

- ЗЕЛЁНЫЙ: из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend` выполнено `npx tsc --noEmit -p tsconfig.app.json` (exit 0).
- КРАСНЫЙ, существующий вне границ атома: из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch` выполнено `python3 scripts/ui/ui_guard.py` (exit 1). Сторож сообщает уже существующий рост экранов-монолитов в `FfFbsOrdersScreen.tsx`, `FfFbsStockSyncScreen.tsx`, `FfFbsSupplyWorkspace.tsx`, `SellerInboundDraftScreen.tsx` и вне карточки — в `WbProductPickerDialog.tsx`; это совпадает с `DESIGN-REVIEW.md`. Текущий атом не менял размер S-04 и не может устранять эти отступления без выхода за контракт.
- ЗЕЛЁНЫЙ: из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend` выполнено `npm run test:unit -- src/ui-kit/WarehouseContextSwitch.test.ts src/ui-kit/WarehouseContextSwitch.runner.test.ts` (2 файла, 14 тестов, exit 0). Отдельного unit-файла S-04 нет; выполнены относящиеся к его складскому контексту регрессии.
- НЕ ЗАПУЩЕН СЦЕНАРИЙ: из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend` выполнено `npx playwright test tests-e2e/ff-fbs-stock-sync.spec.ts -g 'fbs seller warehouses: row binding, manual sync, status panel'`. Playwright не начал сценарий: локальный `webServer` не смог привязаться к `127.0.0.1:18000` (`operation not permitted`, exit 1). Это не обращение к production или внешнему кабинету.
- ЗЕЛЁНЫЙ: из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch` выполнено `git diff --check` (exit 0).
- НЕ СОХРАНЕНО В GIT: выполнено `git add frontend/src/screens/v2/FfFbsStockSyncScreen.tsx frontend/tests-e2e/ff-fbs-stock-sync.spec.ts night/volna-9-recovery/cards/04-warehouse-switch/DEV.md && git diff --cached --check && git commit -m "fix(fbs): shorten stock export label"`. Git не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-1-04-warehouse-switch/index.lock` (`Operation not permitted`), поэтому commit SHA не создан.

## Не реализовано

- По коду и находке R-32 контракта ничего не осталось: `fbs-stock-sync-all` показывает `Выгрузить остатки`, условие включённых привязок остаётся в существующей логике `syncableRows`, а обратная связь остаётся `fbs-stock-sync-feedback`.
- Браузерное выполнение S-04 не подтверждено из-за запрета среды на локальный bind порта. Сам сценарий точечно дополнен, TypeScript и относящиеся unit-регрессии прошли.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных и боевой прод `194.87.96.144` не открывались и не изменялись.
