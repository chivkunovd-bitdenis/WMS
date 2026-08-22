## Изменённые файлы

- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/src/screens/v2/FfFbsPickList.tsx
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/src/screens/v2/fbsApi.ts
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/src/screens/v2/FfFbsPickList.test.ts

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — зелёный.
- `python3 scripts/ui/ui_guard.py` — красный из-за двух посторонних нарушений: `src/components/WbProductPickerDialog.tsx` (экран-монолит 0 → 646) и `src/screens/v2/SellerInboundDraftScreen.tsx` (1111 → 1169). В целевом `FfFbsPickList.tsx` новые нарушения устранены; базовую линию не обновлял.
- `npm run test:unit -- --run src/screens/v2/FfFbsPickList.test.ts` — не запущен: в рабочей копии отсутствует бинарник `vitest` (`sh: vitest: command not found`).

## Не реализовано

- Полные Playwright-сценарии `S-03-TC-001…007` не добавлял: исправление ограничено экраном, API-типами и существующим unit-тестом; окружение frontend не содержит зависимостей для их запуска.
- Backend не изменял: сервер уже возвращает канонические `number_start`, `number_end`, `order_ids` и данные WB-стикера в ответе `order-print-tape`.
