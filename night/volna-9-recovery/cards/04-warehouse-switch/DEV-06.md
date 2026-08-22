# DEV · 04-warehouse-switch · атом 6 · rework

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/App.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/ProductsScreen.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/productsWarehouse.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/ProductsScreen.test.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/tests-e2e/ff-fbs-stock-sync.spec.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/night/volna-9-recovery/cards/04-warehouse-switch/DEV.md`

S-01 теперь получает из общего сессионного контекста только операционные склады и при
смене склада заново запрашивает `/operations/inventory-balances/summary` с его
`warehouse_id`. В таблице меняется только колонка `Остаток`; название, SKU, объём,
селлер и форма товара остаются из исходного каталога. На время смены таблица показывает
`TableSkeletonBody`, а при нуле складов — `EmptyState` с просьбой добавить рабочий склад.

S-04 уже использует общий `useWarehouseContext('fulfillment')`, фильтрует видимые
привязки и доступную массовую синхронизацию по выбранному операционному складу. E2E
дополнен проверкой, что переключение показывает пустую разбивку второго склада и не
вызывает POST публикации остатков. Отдельный сценарий проверяет ноль складов.

`CatalogSection.tsx` не изменялся: по реестру S-01 реализован в `ProductsScreen.tsx`, а
ревью прямо разрешило этот экран и передачу контекста из `App.tsx`. `CatalogSection`
управляет складами и ячейками и не является таблицей товаров S-01.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` из `frontend/` — красный до файлов этого
  атома: `src/screens/v2/FbsSupplyCreateDialog.test.ts:55` содержит JSX в файле `.ts`,
  из-за чего TypeScript выдаёт синтаксические ошибки. Этот соседний тест не входит в
  разрешённый слой атома.
- `python3 scripts/ui/ui_guard.py` из корня — красный на уже накопленных отклонениях:
  `WbProductPickerDialog.tsx`, `FfFbsOrdersScreen.tsx`, `FfFbsStockSyncScreen.tsx`,
  `FfFbsSupplyWorkspace.tsx`, `SellerInboundDraftScreen.tsx`. Новых нарушений в S-01
  и файлах этого прохода guard не показал; baseline не обновлялась.
- `npm run test:unit` из `frontend/` — красный из-за того же соседнего
  `FbsSupplyCreateDialog.test.ts`; остальные 20 файлов и 150 тестов зелёные, включая
  2 новых теста `ProductsScreen.test.ts`.
- `npm run test:unit -- --run src/screens/v2/ProductsScreen.test.ts` — зелёный:
  1 файл, 2 теста.
- `npx eslint src/screens/v2/ProductsScreen.tsx src/screens/v2/productsWarehouse.ts src/screens/v2/ProductsScreen.test.ts tests-e2e/ff-fbs-stock-sync.spec.ts` — зелёный.
- `npx vite build` — зелёный.
- `npx playwright test tests-e2e/ff-fbs-stock-sync.spec.ts --list` — зелёный,
  обнаружены 3 сценария. Живой запуск красный до тестов: sandbox запрещает backend
  привязать `127.0.0.1:18000` (`operation not permitted`).
- `git diff --check` — зелёный.
- Отдельный Git-коммит не создан: sandbox не разрешил создать
  `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-1-04-warehouse-switch/index.lock`
  (`Operation not permitted`). Изменения остаются локальным незакоммиченным diff.

## Не реализовано

- Полный живой Playwright-прогон не выполнен из-за запрета среды на локальный порт;
  сценарии добавлены и успешно разбираются Playwright.
- Три обязательных полных гейта нельзя получить зелёными без правки соседнего атома и
  общей baseline. Эти файлы не менялись, baseline флагом `--update` не двигалась.
- Результат не сохранён в Git из-за запрета записи в служебный каталог worktree;
  восстановимого commit SHA нет.

## Находки

- Секреты, ключи, токены, `.env` и кабинеты учётных данных не читались и не изменялись.
