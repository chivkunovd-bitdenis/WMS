## Изменённые файлы

- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx

Экран использует сохранённый признак `workspace.supply.boxes_without_distribution` для нейтральной шапки. Переключатель доступен при пустых коробах и блокируется только при наличии назначенных заказов; рядом показано объяснение, что сначала нужно убрать назначения из коробов.

Тип workspace и операция переключения уже реализованы предыдущими атомами в текущей ветке:

- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/frontend/src/screens/v2/fbsApi.ts

Файл OpenAPI по указанному в карточке пути отсутствует в checkout. Найденный файл `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/tasks/fbs-operator-flow/openapi/fbs-operations.openapi.json` не входит в разрешённые файлы экрана и не изменялся.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` из frontend — не подтверждён: локальный `tsc` отсутствует (`frontend/node_modules/.bin/tsc` не найден), команда не выдала диагностик.
- `python3 scripts/ui/ui_guard.py` из корня — FAIL: нарушения `экран-монолит` в `src/components/WbProductPickerDialog.tsx` (0 → 646), `src/screens/v2/FfFbsSupplyWorkspace.tsx` (2493 → 2503) и `src/screens/v2/SellerInboundDraftScreen.tsx` (1111 → 1169). Базовую линию не обновлял.
- `npm run test:unit` из frontend — FAIL до запуска тестов: `vitest: command not found`.

## Не реализовано

- Изменение отсутствующего OpenAPI-файла по пути `frontend/openapi/fbs-operations.openapi.json`: файла нет в checkout, а создание или перенос вне разрешённого набора файлов экрана запрещены ролью.

## Находки

- Секреты, ключи, токены, `.env` и кабинеты учётных данных не читались.
- Боевой прод и живой кабинет Wildberries не затрагивались.
