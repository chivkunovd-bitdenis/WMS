## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/frontend/src/screens/v2/FfFbsOrdersScreen.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/frontend/tests-e2e/ff-fbs-orders.spec.ts`

Реализация уже сохранена в коммите `90ae6de`: вердикт отображается в существующей зоне статуса через `StatusChip`, причина — через `TextCell`, без новой колонки и без технических полей WB. Контрактный сценарий покрывает S-03-TC-001, S-03-TC-002, S-03-TC-003 и S-03-TC-006.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — красный: локальный `npx` попытался скачать `tsc`, но сеть недоступна (`ENOTFOUND registry.npmjs.org`), локальный пакет не установлен.
- `python3 scripts/ui/ui_guard.py` — красный из-за новых нарушений в несвязанных файлах `src/components/WbProductPickerDialog.tsx`, `src/screens/v2/FfFbsSupplyWorkspace.tsx`, `src/screens/v2/SellerInboundDraftScreen.tsx`; для `FfFbsOrdersScreen.tsx` зафиксировано улучшение (`свой-чип 2 → 1`, `экран-монолит 1587 → 1574`). Базовая линия не обновлялась.
- `npm run test:unit` — красный: `vitest: command not found`, зависимости frontend в окружении не установлены.

## Не реализовано

Буквально не осталось невыполненных пунктов атомарной фичи. Полную локальную проверку невозможно завершить из-за отсутствующих зависимостей и недоступной сети; несвязанные нарушения `ui_guard.py` не исправлялись в рамках разрешённых файлов.
