# DEV · 04-warehouse-switch · атом 3 (S-14)

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/ff/FfPackagingPage.tsx` — `selectedWarehouseId` явно добавлен в зависимости `useEffect`; ранее сохранённая часть атома читает `useWarehouseContext('fulfillment')`, не запускает список без склада, передаёт `warehouse_id` в `/operations/packaging-tasks` и показывает `WarehouseNoContextState`.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/night/volna-9-recovery/cards/04-warehouse-switch/DEV.md` — записан отчёт роли `screen-dev`.

Основная реализация экрана и зависимость Ф-2 уже сохранены в ветке коммитом `44efc687e8cf22af71ea09db6d7c5485bcfe86b7`; в этом проходе доведена буквальная зависимость `useEffect`, указанная в `FEATURES.md`.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend` — зелёный, код 0, ошибок нет.
- `python3 scripts/ui/ui_guard.py` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch` — красный, код 1. Разрешённый файл `FfPackagingPage.tsx` не назван среди новых нарушений. Скрипт сообщает о ранее существующих монолитах в `WbProductPickerDialog.tsx`, `FfFbsOrdersScreen.tsx`, `FfFbsStockSyncScreen.tsx`, `FfFbsSupplyWorkspace.tsx` и `SellerInboundDraftScreen.tsx`; эти файлы находятся вне атома S-14, базовая линия не изменялась.
- `npm run test:unit -- src/ui-kit/WarehouseContextSwitch.test.ts src/ui-kit/WarehouseContextSwitch.runner.test.ts` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend` — зелёный: 2 файла, 14 тестов прошли.
- `npm run build` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend` — зелёный, production-сборка создана; предупреждение Vite о крупных чанках не является ошибкой сборки.
- `git diff --check` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch` — зелёный, ошибок пробелов нет.
- `git add frontend/src/screens/ff/FfPackagingPage.tsx night/volna-9-recovery/cards/04-warehouse-switch/DEV.md && git commit -m "night(04-warehouse-switch): finalize S-14 warehouse filter"` из корня worktree — не выполнен средой: Git не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-1-04-warehouse-switch/index.lock` (`Operation not permitted`).
- Полные backend `pytest`, `ruff check .` и `mypy .` не запускались согласно запрету атомарной проверки.

## Не реализовано

- Все пункты исходного атома в коде реализованы буквально: текущий склад читается из `useWarehouseContext('fulfillment')`, `warehouse_id` включён в параметры списка, при нулевом складе список не запрашивается и показан `WarehouseNoContextState`, а `selectedWarehouseId` присутствует в зависимостях `useCallback` и `useEffect`.
- Ручной браузерный сценарий «Север → Юг → ноль складов» в роли `screen-dev` не выполнялся: отдельная продуктовая браузерная приёмка этой ролью запрещена. Прямого unit-suite для `FfPackagingPage.tsx` в репозитории нет; выполнены относящиеся к контексту склада unit-тесты.
- Последняя однострочная правка зависимости `useEffect` и этот отчёт локально реализованы, но не сохранены новым коммитом из-за запрета записи в общий Git-каталог worktree. Основная реализация S-14 остаётся сохранённой в `44efc687e8cf22af71ea09db6d7c5485bcfe86b7`.

## Находки

- Новых колонок, чипов и соседних продуктовых изменений не добавлено.
- Секреты, ключи, токены, `.env`, кабинеты учётных данных и боевой production не открывались и не изменялись.
