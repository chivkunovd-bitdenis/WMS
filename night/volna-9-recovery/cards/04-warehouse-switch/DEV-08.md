## Изменённые файлы

- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/TransfersScreen.tsx
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/tests-e2e/transfer-and-outbound.spec.ts

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — выполнялся, процесс не завершился в отведённое время; итог не подтверждён.
- `python3 scripts/ui/ui_guard.py` — красный из-за уже существующих/несвязанных новых нарушений в `WbProductPickerDialog.tsx`, `FfFbsStockSyncScreen.tsx`, `FfFbsSupplyWorkspace.tsx` и `SellerInboundDraftScreen.tsx`; эти файлы не входят в разрешённые файлы S-25.
- `npm run test:unit` — красный: в окружении отсутствует команда `vitest` (`vitest: command not found`).

## Не реализовано

- Полная фильтрация строк S-25 текущим складом и раскрытие реальной межскладской пары не реализованы буквально: текущий экран получает только `locations`, `products` и POST-обработчик, без списка движений, названий складов или выбранного складского контекста; доступный API также отклоняет перемещение между разными складами. В разрешённых файлах добавлено единое видимое представление отправленной операции «из ячейки → в ячейку» и e2e-проверка этого результата.
