## Изменённые файлы

В рамках этого прохода файлы ui-kit не изменялись: реализация атома уже содержит требуемые состояния и экспортируется через `frontend/src/ui-kit/index.ts`.

Проверенные файлы:

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/src/ui-kit/ModalFrame.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/src/ui-kit/FilterBar.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/src/ui-kit/Cells.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/src/ui-kit/Actions.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/src/ui-kit/index.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/src/ui-kit/UiKitShowcase.tsx`

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — не завершён: процесс завис без вывода и остановлен вручную; ранее локальный `tsc` также отсутствовал.
- `python3 scripts/ui/ui_guard.py` — красный из-за двух новых нарушений вне атома: `frontend/src/components/WbProductPickerDialog.tsx` и `frontend/src/screens/v2/SellerInboundDraftScreen.tsx`. Базовая линия не изменялась; для `FfFbsPickList.tsx` нарушений стало меньше.
- `npm run test:unit -- --run src/ui-kit` — не запущен: `vitest: command not found`.

## Не реализовано

- Находки 1–7 из `REVIEW.md` относятся к `FfFbsPickList.tsx`, `FbsPrintPreviewDialog.tsx`, API и backend; эти файлы не входят в разрешённую границу screen-dev и не изменялись.
- Живой browser-review не выполнялся: задача ограничена переиспользуемыми ui-kit элементами, а frontend-зависимости для unit-тестов отсутствуют.
- Секреты, ключи, токены, `.env` и кабинеты учётных данных не читались.
