# Screen dev — 03-no-distribution-mode — фича 4

## Изменённые файлы

- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx

Экран использует сохранённый признак `workspace.supply.boxes_without_distribution` как источник истины для нейтральной шапки. Поэтому режим не сбрасывается визуально после удаления и повторного создания пустых коробов. Переключатель остаётся доступным без назначений и блокируется только при наличии назначенных заказов; tooltip объясняет, что сначала нужно убрать назначения из коробов.

Изменения API-типа и операции переключения уже присутствовали в предыдущем атоме в текущей ветке:

- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/frontend/src/screens/v2/fbsApi.ts

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` (из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/frontend`) — PASS.
- `python3 scripts/ui/ui_guard.py` (из корня) — FAIL: существующие/предыдущие нарушения `экран-монолит` в `src/components/WbProductPickerDialog.tsx` (0 → 646), `src/screens/v2/FfFbsSupplyWorkspace.tsx` (2493 → 2503) и `src/screens/v2/SellerInboundDraftScreen.tsx` (1111 → 1169). Базовую линию не обновлял.
- `npm run test:unit` (из frontend) — FAIL до запуска тестов: `vitest: command not found`.

## Не реализовано

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/frontend/openapi/fbs-operations.openapi.json` отсутствует в checkout. Фактический OpenAPI-файл находится в `tasks/fbs-operator-flow/openapi`, но он не входит в разрешённые файлы экрана S-03, поэтому не изменялся.

## Находки

- Секреты, ключи, токены, `.env` и кабинеты учётных данных не читались.
- Боевой прод и живой кабинет Wildberries не затрагивались.
