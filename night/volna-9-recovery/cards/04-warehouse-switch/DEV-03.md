# DEV · 04-warehouse-switch · атом 3 (S-14)

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/ff/FfPackagingPage.test.ts` — добавлен атомарный регрессионный unit-тест `S-14-TC-001`: он фиксирует передачу `warehouse_id`, перезагрузку при смене `selectedWarehouseId`, ранний выход без запроса и показ `WarehouseNoContextState` при нулевом складском контексте.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/night/volna-9-recovery/cards/04-warehouse-switch/DEV.md` — записан обязательный отчёт роли `screen-dev`.

Экранная реализация в `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/ff/FfPackagingPage.tsx` уже находилась в текущей ветке: основная часть сохранена коммитом `44efc687e8cf22af71ea09db6d7c5485bcfe86b7`, а буквальная зависимость `selectedWarehouseId` в `useEffect` — коммитом `4a15595402a90d2b1518d057895e4632d2d1f2d7`. Повторно переписывать корректный экран не потребовалось.

## Гейты

- `npm run test:unit -- src/screens/ff/FfPackagingPage.test.ts` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend` — зелёный, код 0: 1 файл, 2 теста прошли.
- `npx tsc --noEmit -p tsconfig.app.json` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend` — зелёный, код 0, ошибок нет.
- `python3 scripts/ui/ui_guard.py` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch` — красный, код 1. Разрешённый экран `FfPackagingPage.tsx` и его тест среди новых нарушений не названы. Скрипт сообщает о ранее существующих монолитах вне атома: `WbProductPickerDialog.tsx` (0 → 646), `FfFbsOrdersScreen.tsx` (1587 → 1690), `FfFbsStockSyncScreen.tsx` (1083 → 1121), `FfFbsSupplyWorkspace.tsx` (2493 → 2605) и `SellerInboundDraftScreen.tsx` (1111 → 1267). Базовая линия не изменялась.
- `npm run build` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend` — зелёный, код 0; Vite собрал production bundle. Предупреждение о крупных чанках не является ошибкой.
- `git diff --check` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch` — зелёный, ошибок пробелов нет.
- `git add frontend/src/screens/ff/FfPackagingPage.test.ts night/volna-9-recovery/cards/04-warehouse-switch/DEV.md` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch` — красный: Git не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-1-04-warehouse-switch/index.lock` (`Operation not permitted`). Поэтому новый commit и push этого прохода технически невозможны в текущем sandbox.
- Полные backend `pytest`, `ruff check .` и `mypy .` не запускались согласно прямому запрету атомарной проверки.

## Не реализовано

- Все пункты атома в разрешённом экранном файле реализованы буквально: используется `useWarehouseContext('fulfillment')`; без `selectedWarehouseId` список очищается и запрос не выполняется; параметр `warehouse_id` передаётся в `/operations/packaging-tasks`; `selectedWarehouseId` входит в зависимости `useCallback` и `useEffect`; при нулевом контексте показан `WarehouseNoContextState`. Новых колонок, чипов и действий не добавлено.
- Ручной браузерный сценарий «Север → Юг → ноль складов» не выполнялся: роль `screen-dev` реализует экран и технические проверки, а живая продуктовая браузерная приёмка должна выполняться отдельной ролью после разработки.
- Общий `ui_guard.py` не зелёный из-за пяти чужих файлов вне разрешённой области этого атома; исправлять их или обновлять baseline роль `screen-dev` не имеет права.
- Новый unit-тест и текущая версия `DEV.md` локально реализованы, но не сохранены новым коммитом и не опубликованы из-за запрета записи в общий Git-каталог worktree. Основная экранная реализация S-14 остаётся сохранённой в коммитах `44efc687e8cf22af71ea09db6d7c5485bcfe86b7` и `4a15595402a90d2b1518d057895e4632d2d1f2d7`.

## Находки

- Из трёх пунктов `REVIEW.md` к этому атому и разрешённому файлу относится только находка 1 по S-14. Находки 2 (S-28 backend) и 3 (гонка S-03) не затрагивались.
- Секреты, ключи, токены, `.env`, кабинеты учётных данных и боевой production не открывались и не изменялись.
