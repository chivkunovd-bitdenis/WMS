## Изменённые файлы

- Изменений в продуктовых файлах нет.
- Артефакт: `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/night/volna-9-recovery/cards/04-warehouse-switch/DEV.md`

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — не удалось получить подтверждённый результат: процесс `npx` завершился без вывода и статуса в отведённое время.
- `python3 scripts/ui/ui_guard.py` — красный из-за новых нарушений в несвязанных экранах `WbProductPickerDialog.tsx`, `FfFbsOrdersScreen.tsx`, `FfFbsStockSyncScreen.tsx`, `FfFbsSupplyWorkspace.tsx`, `SellerInboundDraftScreen.tsx`; S-25 не указан среди нарушений.
- `npm run test:unit` — красный: `vitest: command not found`.

## Не реализовано

- Полная фильтрация строк S-25 текущим складом и раскрытие межскладской пары не легли буквально. `TransfersScreen` получает только `locations`, `products` и обработчик POST, без списка движений, названий операционных складов и выбранного сессионного контекста. Добавление этих данных потребовало бы правки `App.tsx`/API вне разрешённых файлов атома.
- Текущий экран поддерживает только обычное перемещение между ячейками и показывает подтверждение последней операции без UUID. Межскладской pick с одной раскрываемой парой должен быть поставлен после передачи в экран необходимых данных от зависимых атомов 4, 5 и 11.

