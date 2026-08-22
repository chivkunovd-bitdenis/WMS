## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/src/screens/v2/fbsApi.ts` — добавлены необязательные серверные поля номера заказа и связанного WB-заказа для предпросмотра.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx` — полная печать всегда отправляет все ID заказов поставки.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/src/screens/v2/FbsPrintPreviewDialog.tsx` — предпросмотр показывает пару WB-стикер → служебная этикетка WMS и складское сообщение для пропущенного стикера.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json`: выполнялся, процесс не завершился в отведённое время; итог не подтверждён.
- `python3 scripts/ui/ui_guard.py`: BLOCKED существующими/затронутыми нарушениями монолитных экранов; после сокращения добавленной разметки нарушение `FfFbsSupplyWorkspace.tsx` устранено, остаются `WbProductPickerDialog.tsx` и `SellerInboundDraftScreen.tsx`.
- `npm run test:unit`: BLOCKED — в окружении отсутствует команда `vitest` (`sh: vitest: command not found`).
- Commit: BLOCKED — Git не может создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-3-06-picking-list-order/index.lock` из-за прав общей мета-папки worktree; SHA не получен.

## Не реализовано

- Если сервер не прислал `order_number`, `wb_order_id` или связанный номер в объекте ассета, интерфейс показывает `—`; клиент не подменяет серверную нумерацию локальным порядком.

## Находки

- Секреты, ключи, токены и `.env` не читались. Боевой прод и кабинет Wildberries не затрагивались.
