## Изменённые файлы

- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/src/screens/v2/FfFbsPickList.tsx
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/src/screens/v2/FfFbsPickList.test.ts

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — не получил завершения: процесс завис без вывода и был остановлен.
- `python3 scripts/ui/ui_guard.py` — красный из-за двух новых нарушений вне границы атома: `frontend/src/components/WbProductPickerDialog.tsx` и `frontend/src/screens/v2/SellerInboundDraftScreen.tsx`. Для `FfFbsPickList.tsx` нарушений стало меньше.
- `npm run test:unit -- --run src/screens/v2/FfFbsPickList.test.ts` — не запущен: `vitest: command not found`.
- Commit — не создан: Git не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-3-06-picking-list-order/index.lock` из-за ограничения доступа рабочей среды.

## Не реализовано

- E2E-сценарии `S-03-TC-001…007` в этом проходе не добавлялись: для их полноценного запуска в рабочей копии отсутствует установленный test runner, а существующий e2e-файл не содержит подготовленного сценария открытия модалки листа подбора.
- В пределах разрешённых файлов печать переведена на канонический `order-print-tape` и блокируется на время подготовки; отдельная существующая preview-компонента и серверные типы не изменялись, поскольку они не входят в границу атома.
