# DEV · 04-warehouse-switch · screen-dev

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/FfFbsStockSyncScreen.tsx` — непривязанные WB-склады остаются видимыми при выборе любого операционного склада, чтобы оператор мог создать первую привязку; привязанные строки по-прежнему фильтруются выбранным складом.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/night/volna-9-recovery/cards/04-warehouse-switch/DEV.md` — обязательный отчёт screen-dev.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend` — не подтверждён: команда не вывела результат в рабочей копии.
- `python3 scripts/ui/ui_guard.py` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch` — не подтверждён: команда не вывела результат в рабочей копии.
- `npm run test:unit` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend` — не подтверждён: команда не вывела результат в рабочей копии.
- `git diff --check` — зелёный.

## Не реализовано

- Остальные находки из `REVIEW.md` относятся к backend, другим экранам или документации и не входят в разрешённый слой этого атома.
- Полный браузерный сценарий с двумя операционными складами не добавлялся: контракт разрешает только перечисленные файлы, а существующий e2e-файл не содержит готового сценария для настройки двух складов без изменений за пределами этого атома.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных и боевой прод не читались и не изменялись.
