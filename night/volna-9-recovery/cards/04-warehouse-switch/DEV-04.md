## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/ui-kit/WarehouseContextSwitch.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/ui-kit/WarningNotice.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/ui-kit/index.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/ui-kit/WarehouseContextSwitch.test.tsx`

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — красный: локальный `tsc` отсутствует, а загрузка через `npx` невозможна из-за отсутствия сети (`ENOTFOUND registry.npmjs.org`).
- `python3 scripts/ui/ui_guard.py` — красный на уже существующих нарушениях вне разрешённых файлов: `src/components/WbProductPickerDialog.tsx`, `src/screens/v2/FfFbsSupplyWorkspace.tsx`, `src/screens/v2/SellerInboundDraftScreen.tsx`. Новых нарушений в изменённых ui-kit-файлах не выявлено.
- `npm run test:unit` — красный: локальный бинарник `vitest` отсутствует (`vitest: command not found`).

## Не реализовано

Буквально не проверено только прохождение обязательных локальных гейтов из-за отсутствующих зависимостей и недоступной сети. Реализация контракта добавлена: переключатель скрывается при 0–1 варианте, открывает список имён, вызывает `onChange` и закрывается после выбора; загрузка и недоступность объясняются оператору, ошибка выводится через `ErrorNotice`, `WarningNotice` остаётся неблокирующим.

Отдельный Git-коммит не создан: среда запрещает запись `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-1-04-warehouse-switch/index.lock` (`Operation not permitted`).
