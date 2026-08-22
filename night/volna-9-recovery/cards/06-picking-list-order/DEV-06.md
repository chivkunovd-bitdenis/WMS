## Изменённые файлы

- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/src/screens/v2/FfFbsPickList.tsx
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/src/screens/v2/FfFbsPickList.test.ts

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — не подтверждён: в `frontend/node_modules` отсутствует локальный `tsc`, а `npx` не смог предоставить исполняемый пакет в текущем окружении.
- `python3 scripts/ui/ui_guard.py` — затронутый экран улучшен: нарушения `свой-чип`, `своя-кнопка` и `своя-таблица` для `FfFbsPickList.tsx` устранены. Общий запуск красный из-за двух ранее существовавших нарушений в `src/components/WbProductPickerDialog.tsx` и `src/screens/v2/SellerInboundDraftScreen.tsx`; базовая линия не изменялась.
- `npm run test:unit -- --run src/screens/v2/FfFbsPickList.test.ts` — не подтверждён: `vitest: command not found`.

## Не реализовано

- `frontend/tests-e2e/ff-fbs-supply.spec.ts` не изменялся: в текущем окружении отсутствуют зависимости для запуска Playwright, а сценарий открытия модалки находится в существующем рабочем потоке S-03 и требует его полного fixture-контекста.
- Предпросмотр пар «стикер WB → служебная этикетка WMS» не добавлялся в этот экран: контракт карточки оставляет генерацию полной ленты серверной ручке `generateFbsSupplyStickers`; экран сохраняет полный вызов печати независимо от фильтра и отметок.
