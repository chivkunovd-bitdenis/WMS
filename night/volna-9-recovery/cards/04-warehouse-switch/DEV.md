# DEV · 04-warehouse-switch · feature 1

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/ff/FfPackagingPage.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/ff/FfPackagingPage.test.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/night/volna-9-recovery/cards/04-warehouse-switch/DEV.md`

Открытое задание упаковки использует склад самого задания в `WarehouseContextSwitch`, а переключатель заблокирован с причиной `Склад закреплён: открыто задание упаковки`. Сессионный контекст по-прежнему применяется к очереди. Целевой тест покрывает прямую ссылку на задание «Север» при контексте «Юг», проверяет отсутствие вызова `onWarehouseChange` и данные панели «Север»; существующий тест очереди покрывает смену «Север» → «Юг».

## Гейты

- Зелёный: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend && npx tsc --noEmit -p tsconfig.app.json`.
- Зелёный: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend && npm run test:unit -- --run src/screens/ff/FfPackagingPage.test.ts` — `1 passed`, `3 passed`.
- Красный вне границ этого атома: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch && python3 scripts/ui/ui_guard.py`. Новые нарушения только в чужих файлах: `frontend/src/components/WbProductPickerDialog.tsx`, `frontend/src/screens/v2/FfFbsOrdersScreen.tsx`, `frontend/src/screens/v2/FfFbsStockSyncScreen.tsx`, `frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx`, `frontend/src/screens/v2/SellerInboundDraftScreen.tsx`. Для `frontend/src/screens/ff/FfPackagingPage.tsx` guard сообщает улучшение `2146 → 2143`; базовую линию не обновляли.
- Зелёный: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch && git diff --check`.
- Не выполнен из-за sandbox: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch && git add frontend/src/screens/ff/FfPackagingPage.tsx frontend/src/screens/ff/FfPackagingPage.test.ts night/volna-9-recovery/cards/04-warehouse-switch/DEV.md && git diff --cached --check && git commit -m "fix(packaging): lock task warehouse context"` — Git не может создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-1-04-warehouse-switch/index.lock`: `Operation not permitted`.

## Не реализовано

Нет. Реализован только атом 1 из `FEATURES.md`; backend/CI-проверка конкурентной смены склада S-28 намеренно не затрагивалась. Отдельный Git-коммит создать нельзя: sandbox не разрешает запись в общий каталог `.git` зарегистрированного worktree.

## Находки

`ui_guard.py` остаётся красным из-за новых нарушений в файлах других атомов. Секреты, ключи, токены, `.env`, кабинеты учётных данных, боевой production и живой Wildberries не открывались и не изменялись.
