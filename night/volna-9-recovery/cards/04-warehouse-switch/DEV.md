# DEV · 04-warehouse-switch · атом 1

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/FfFbsOrdersScreen.tsx` — убран внешний дублирующий `Alert`; единственное сообщение об ошибке остаётся в `WarehouseContextSwitch` как `ErrorNotice`.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/tests-e2e/ff-fbs-supply.spec.ts` — добавлен сценарий ошибки загрузки складов: проверяет один текст внутри `fbs-wms-warehouse-context` и отсутствие внешнего `fbs-wms-warehouse-context-error`.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/night/volna-9-recovery/cards/04-warehouse-switch/DEV.md` — отчёт роли screen-dev.

## Гейты

- ЗЕЛЁНЫЙ: из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend` выполнено `npx tsc --noEmit -p tsconfig.app.json` (exit 0).
- КРАСНЫЙ, вне границы атома: из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch` выполнено `python3 scripts/ui/ui_guard.py` (exit 1). Сторож уже фиксирует рост экранов-монолитов в `FfFbsOrdersScreen.tsx`, `FfFbsStockSyncScreen.tsx`, `FfFbsSupplyWorkspace.tsx`, `SellerInboundDraftScreen.tsx` и вне границы карточки `WbProductPickerDialog.tsx`; это совпадает с `DESIGN-REVIEW.md`. Текущий атом сократил `FfFbsOrdersScreen.tsx` с 1676 до 1670 строк и не может исправлять остальные экраны или менять baseline.
- ЗЕЛЁНЫЙ: из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend` выполнено `npm run test:unit -- src/ui-kit/WarehouseContextSwitch.test.ts` (1 файл, 7 тестов, exit 0).
- НЕ ЗАПУЩЕНЫ ТЕСТЫ: из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend` выполнено `npx playwright test tests-e2e/ff-fbs-supply.spec.ts --grep 'WMS warehouse context is sent to the server|warehouse load error is shown once in the context'`. Playwright не начал сценарии: его локальный `webServer` не смог привязаться к `127.0.0.1:18000` (`operation not permitted`), exit 1. Это не обращение к продакшену или внешнему кабинету.
- НЕ СОХРАНЕНО В GIT: выполнено `git add frontend/src/screens/v2/FfFbsOrdersScreen.tsx frontend/tests-e2e/ff-fbs-supply.spec.ts night/volna-9-recovery/cards/04-warehouse-switch/DEV.md && git diff --cached --check && git commit -m "fix(fbs): show warehouse load error once"`. Git не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-1-04-warehouse-switch/index.lock` (`Operation not permitted`), поэтому индекс и commit SHA не созданы.

## Не реализовано

- По коду контракта и находке R-23 ничего не осталось: в S-03 существует ровно один `ErrorNotice` с текстом `Не удалось загрузить склады. Обновите страницу.` внутри `fbs-wms-warehouse-context`; внешнего сообщения больше нет.
- Фактический прогон двух Playwright-сценариев не подтверждён из-за запрета среды на локальный bind порта. Сценарий ошибки добавлен и проверен TypeScript-компилятором, но браузерное выполнение требует среды, где разрешён `127.0.0.1:18000`.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных и боевой прод `194.87.96.144` не открывались и не изменялись.
