# DEV · 04-warehouse-switch · screen-dev

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/FfFbsStockSyncScreen.tsx` — добавлен контекст выбранного операционного склада, фильтрация отображаемых WB-привязок и `EmptyState` для нулевого числа рабочих складов.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — не подтверждён: локальный `npx` не вернул результат в доступное время, установка зависимостей в среде недоступна.
- `python3 scripts/ui/ui_guard.py` — красный: существующие нарушения в `src/components/WbProductPickerDialog.tsx`, `src/screens/v2/FfFbsSupplyWorkspace.tsx`, `src/screens/v2/SellerInboundDraftScreen.tsx`; для изменённого `src/screens/v2/FfFbsStockSyncScreen.tsx` guard также отметил рост монолитного экрана. Базовую линию не обновлял.
- `npm run test:unit` — красный: `vitest: command not found`.

## Не реализовано

- S-01 не расширялся отдельной товарной таблицей: переданный `CatalogSection` не содержит таблицы товарных остатков, а уже существующий выбор склада применяет склад к доступным складским данным и ячейкам. Добавление нового источника данных вышло бы за границы этого экранного куска.
- E2E-сценарий для переключения не добавлен: для него требуется тестовая фикстура с несколькими операционными WMS-складами и привязками, а локальный `test:unit` не запускается из-за отсутствующего `vitest`.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных и боевой прод не читались и не изменялись.
