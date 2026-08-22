# DEV · 04-warehouse-switch · атом 5 · rework

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/App.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/contexts/WarehouseContext.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/FfFbsOrdersScreen.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/FfFbsStockSyncScreen.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/utils/fbsWarehouse.test.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/night/volna-9-recovery/cards/04-warehouse-switch/DEV.md`

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` из `frontend/` — **красный до файлов этого атома**: уже закоммиченный `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/FbsSupplyCreateDialog.test.ts` содержит JSX в файле `.ts` (ошибки синтаксиса с строки 55). При первом прогоне до восстановления зависимостей команда ошибочно завершилась без диагностики; после `npm ci --ignore-scripts --prefer-offline` запустился реальный локальный TypeScript и показал дефект соседнего теста.
- `python3 scripts/ui/ui_guard.py` из корня — **красный на ранее накопленном diff ветки**: `WbProductPickerDialog.tsx`, `FfFbsOrdersScreen.tsx`, `FfFbsStockSyncScreen.tsx`, `FfFbsSupplyWorkspace.tsx`, `SellerInboundDraftScreen.tsx`. Baseline не обновлялась. Собственная дельта rework не увеличивает `FfFbsOrdersScreen.tsx` относительно `HEAD` (1663 → 1663 строки), а `FfFbsStockSyncScreen.tsx` уменьшает (1132 → 1120 строк).
- `npm run test:unit` из `frontend/` — **красный до файлов этого атома**: 19 файлов и 148 тестов зелёные, единственный suite `FbsSupplyCreateDialog.test.ts` не преобразуется из-за JSX в `.ts`.
- `npm run test:unit -- --run src/utils/fbsWarehouse.test.ts` — **зелёный**, 1 файл, 6 тестов. Подтверждены: автоподстановка единственного склада, выбор primary вместо `list[0]`, восстановление выбора текущей сессии, отказ от отсутствующего/служебного склада.
- `git diff --check` — **зелёный**.
- Сохранение отдельным Git-коммитом — **заблокировано правами среды**: Git не может создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-1-04-warehouse-switch/index.lock` (`Operation not permitted`). Изменения остались только в рабочем дереве; commit SHA отсутствует.

## Не реализовано

- Три обязательных полных гейта нельзя получить зелёными без правки уже закоммиченных файлов соседних атомов и общей baseline; роль `screen-dev` запрещает такой выход за границы. Baseline флагом `--update` не двигалась.
- Отдельный глобальный контекст склада в seller-портал не добавлялся намеренно: по контракту `SellerApp.tsx` уже передаёт склад только как реквизит заявки, автоматически подставляет единственный склад и очищает загруженный список после logout.
- Живой browser/e2e-сценарий не запускался: в обязательные гейты роли он не входит, а полный unit/tsc слой уже блокируется перечисленным дефектом соседнего теста.
- Публикация в Git не выполнена: общий Git-каталог зарегистрированного worktree недоступен для записи в текущей песочнице. Создание второго репозитория или временного клона не использовалось.

## Находки

- Находка review №4 для слоя атома исправлена: `App`, S-03 и S-04 используют один fulfillment-ключ и одно событие сессионного контекста; локальный ключ S-03 удалён.
- Связанная находка review №5 закрыта в S-03: при нуле операционных складов очередь не показывает данные всех складов и выводит `EmptyState` «Нет рабочего склада» без складских действий.
