# DEV · 04-warehouse-switch · screen-dev

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/utils/fbsWarehouse.ts` — фильтрация операционных складов и выбор сохранённого/первичного склада.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/contexts/WarehouseContext.tsx` — сессионный контекст склада для FF и селлера с очисткой при logout.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/App.tsx` — подключён контекст FF и очищен выбор при выходе.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/apps/seller/SellerApp.tsx` — подключён отдельный контекст селлера, без глобального фильтра заявок.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — не подтверждён: локальный `tsc` отсутствует, а `npx` завис без результата в среде без доступной установки зависимостей.
- `python3 scripts/ui/ui_guard.py` — красный на существующих нарушениях вне изменённых файлов: `src/components/WbProductPickerDialog.tsx`, `src/screens/v2/FfFbsSupplyWorkspace.tsx`, `src/screens/v2/SellerInboundDraftScreen.tsx`; новых нарушений в изменённых файлах не выявлено. `src/App.tsx` стал меньше по размеру.
- `npm run test:unit` — красный: `vitest: command not found`.

## Не реализовано

- Визуальный `WarehouseContextSwitch` и отдельные экранные фильтры не изменялись: они относятся к уже реализованному UI-kit-атому и другим атомарным кускам карточки.
- Полный запуск типизации и unit-тестов невозможен без локальных зависимостей; сеть для их установки недоступна.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных и боевой прод не читались и не изменялись.
