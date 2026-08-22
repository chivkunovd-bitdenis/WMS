# DEV · 04-warehouse-switch · screen-dev

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/tests-e2e/ff-fbs-supply.spec.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/night/volna-9-recovery/cards/04-warehouse-switch/DEV.md`

Изменён только экран рабочего места FBS и его пользовательский E2E-сценарий. Повторный товарный скан получает стабильный ключ для той же ячейки и заказа, поэтому повтор запроса возвращает прежний результат. Сценарий также проверяет скан склада, последующий выбор ячейки и неизменность строки «Взято…» при повторе.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — не подтверждён: локальный процесс `npx` завис без вывода и был остановлен после ожидания; результат не объявляю зелёным.
- `python3 scripts/ui/ui_guard.py` — КРАСНЫЙ: храповик сообщил новые нарушения в `WbProductPickerDialog.tsx`, `FfFbsOrdersScreen.tsx`, `FfFbsStockSyncScreen.tsx`, `FfFbsSupplyWorkspace.tsx` и `SellerInboundDraftScreen.tsx`. Базовую линию не обновлял.
- `npm run test:unit` — КРАСНЫЙ: `vitest: command not found`.
- `git diff --check` — зелёный.

## Не реализовано

- Полный продуктовый browser review не выполнялся: роль screen-dev ограничена кодом и обязательными локальными gate-командами.
- `frontend/src/screens/v2/fbsApi.ts` и `frontend/src/ui-kit/ScannerLine.tsx` не потребовали изменений: существующие resolver/client и текстовые состояния уже соответствуют контракту.
