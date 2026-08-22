## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/FfFbsOrdersScreen.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/tests-e2e/ff-fbs-supply.spec.ts`

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` (из `frontend/`) — зелёный.
- `python3 scripts/ui/ui_guard.py` (из корня) — красный: храповик фиксирует новые уже существующие превышения размера экранов, в том числе `FfFbsOrdersScreen.tsx` (1587 → 1664) и `FfFbsSupplyWorkspace.tsx` (2493 → 2605). Базовую линию не обновлял.
- `npm run test:unit -- --run src/screens/v2/FfFbsSupplyWorkspace.test.ts` (из `frontend/`) — не запустился: `vitest: command not found` в данной рабочей копии.
- `git diff --check` — зелёный.

## Не реализовано

- Серверная фильтрация FBS-worklist по WMS-складу не добавлена: текущий API принимает только WB-склад. Экран дочитывает все страницы при выбранном WMS-контексте и фильтрует по физическому складу, поэтому записи за первой страницей не скрываются, но параметр на сервере должен добавить backend-атом.

## Находки

- Секреты, ключи, токены, `.env` и кабинеты учётных данных не читались.
