# DEV · 04-warehouse-switch · атом 6

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/FfFbsStockSyncScreen.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/night/volna-9-recovery/cards/04-warehouse-switch/DEV.md`

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` (каталог `frontend/`) — зелёный.
- `python3 scripts/ui/ui_guard.py` (корень) — красный: базовая линия уже отстаёт в пяти экранах; для S-04 показано `экран-монолит 1083 → 1133`. Базовую линию не обновлял.
- `npm run test:unit` (каталог `frontend/`) — не запустился: `sh: vitest: command not found`.
- `git diff --check` — зелёный. Commit не создан: Git запретил создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-1-04-warehouse-switch/index.lock` (`Operation not permitted`).

## Не реализовано

- S-01 буквально не реализован. В реестре экран S-01 — `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/ProductsScreen.tsx`, а исходный список атома называет `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/sections/CatalogSection.tsx`, который является администрированием складов и ячеек. Находка review №12 требует ещё и передачу данных из `App.tsx`; этот файл не разрешён для данного атома и роли.
- E2E-сценарий не менялся: имеющийся сценарий работает через значение авторизации из `localStorage`; профиль роли запрещает читать токены.

## Находки

- S-04: при нуле операционных складов остаётся только `EmptyState` с просьбой добавить рабочий склад; фильтры, таблица и действия публикации не показываются. При выбранном складе таблица и кнопка синхронизации ограничены только его активными привязками. Смена контекста не вызывает публикацию.
