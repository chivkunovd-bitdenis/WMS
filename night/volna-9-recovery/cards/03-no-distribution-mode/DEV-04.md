# Screen dev — 03-no-distribution-mode

## Изменённые файлы

- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/frontend/src/screens/v2/fbsApi.ts
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — PASS.
- `python3 scripts/ui/ui_guard.py` — FAIL: сообщает о новых нарушениях «экран-монолит» для `src/screens/v2/FfFbsSupplyWorkspace.tsx` (2493 → 2503), а также для существующих затронутых файлов `WbProductPickerDialog.tsx` и `SellerInboundDraftScreen.tsx`; базовая линия не обновлялась.
- `npm run test:unit` — FAIL: `vitest: command not found`, локальные зависимости для unit-тестов не установлены.

## Не реализовано

- OpenAPI-файл по указанному в карточке пути `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/frontend/openapi/fbs-operations.openapi.json` отсутствует. Фактический файл находится в `tasks/fbs-operator-flow/openapi`, но он не входит в разрешённый список файлов экранного реестра, поэтому не изменялся.

## Находки

- Секреты, ключи, токены и `.env` не читались.
