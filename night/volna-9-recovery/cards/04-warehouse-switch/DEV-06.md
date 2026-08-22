# DEV · 04-warehouse-switch · атом 6

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/FfFbsStockSyncScreen.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/night/volna-9-recovery/cards/04-warehouse-switch/DEV.md`

Экран S-04 переведён на общий `useWarehouseContext('fulfillment')`: загрузка складов заполняет единый контекст, выбор публикует его событие, а изменения контекста на другом экране обновляют S-04. Фильтр строк и остатки по-прежнему используют только выбранный операционный WMS-склад; WB-склады не участвуют в выборе и не публикуются при смене контекста.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — зелёный.
- `python3 scripts/ui/ui_guard.py` — красный из-за уже существующих нарушений храповика: `FfFbsStockSyncScreen.tsx` `экран-монолит 1083 → 1124` (в `HEAD` тот же размер файла; baseline уже отстаёт). Флаг `--update` не применялся.
- `npm run test:unit` — не запустился: в окружении отсутствует команда `vitest` (`sh: vitest: command not found`).

## Не реализовано

- Из находок ревью вне разрешённых файлов атома (API preflight, S-03, S-14, backend и другие экраны) ничего не менялось.
- В `CatalogSection.tsx` отдельного списка складских количеств товара нет: этот файл содержит каталог ячеек, поэтому добавлять неподтверждённую разметку остатков в него нельзя.
