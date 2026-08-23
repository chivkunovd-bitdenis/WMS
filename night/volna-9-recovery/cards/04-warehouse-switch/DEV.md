# DEV · 04-warehouse-switch · атом 2

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/FfFbsStockSyncScreen.tsx` — реализация атома уже сохранена в commit `9136dc95`: главная кнопка `fbs-stock-sync-all` показывает `Выгрузить остатки`; условие доступности `syncableRows` и запуск существующей выгрузки не изменены.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/tests-e2e/ff-fbs-stock-sync.spec.ts` — в том же commit сценарий S-04 проверяет короткую подпись, недоступность на складе без строк для выгрузки и видимую обратную связь `fbs-stock-sync-feedback` после нажатия.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/night/volna-9-recovery/cards/04-warehouse-switch/DEV.md` — восстановлен обязательный артефакт роли screen-dev после удаления из рабочего дерева.

## Гейты

- ЗЕЛЁНЫЙ: из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend` выполнено `npx tsc --noEmit -p tsconfig.app.json` (exit 0).
- КРАСНЫЙ: из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch` выполнено `python3 scripts/ui/ui_guard.py` (exit 1). Сторож сообщает ранее известные новые отступления в `FfFbsStockSyncScreen.tsx` (1083 → 1121), `FfFbsOrdersScreen.tsx`, `FfFbsSupplyWorkspace.tsx`, `SellerInboundDraftScreen.tsx` и `WbProductPickerDialog.tsx`. Устранять их в этом атоме означало бы менять код за пределами сокращения подписи; baseline флагом `--update` не менялась.
- ЗЕЛЁНЫЙ: из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend` выполнено `npm run test:unit -- src/ui-kit/WarehouseContextSwitch.test.ts src/ui-kit/WarehouseContextSwitch.runner.test.ts` (2 файла, 14 тестов, exit 0). Отдельного unit-файла S-04 нет; выполнены относящиеся к его складскому контексту регрессии.
- НЕ ЗАПУЩЕН СЦЕНАРИЙ: из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend` выполнено `npx playwright test tests-e2e/ff-fbs-stock-sync.spec.ts --grep 'fbs seller warehouses: row binding, manual sync, status panel'`. Локальный `webServer` не смог привязаться к `127.0.0.1:18000` (`operation not permitted`, exit 1), поэтому единственный точечный browser-сценарий не стартовал.

## Не реализовано

- По коду атом реализован буквально: подпись `fbs-stock-sync-all` — `Выгрузить остатки`; при отсутствии строк для выгрузки кнопка остаётся недоступной, а успешный запуск показывает существующий `fbs-stock-sync-feedback`.
- Нельзя подтвердить browser-выполнение в этой среде из-за запрета на привязку локального порта `127.0.0.1:18000`. TypeScript и относящиеся unit-регрессии прошли.
- `ui_guard.py` не зелёный из-за ранее существовавших экранных отступлений. Их исправление не входит в разрешённые файлы и в единственное изменение этого атома.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных, живой Wildberries и боевой прод `194.87.96.144` не открывались и не изменялись.
