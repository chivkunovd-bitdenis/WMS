# DEV · 04-warehouse-switch · атом 9

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/fbsApi.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/FbsSupplyCreateDialog.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/FbsSupplyCreateDialog.test.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/tests-e2e/ff-fbs-supply.spec.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/night/volna-9-recovery/cards/04-warehouse-switch/DEV.md`

Исправлено чтение реального ответа preflight: `stock_preflight`, варианты и рекомендация склада, а также строки остатков теперь берутся из верхнего уровня API. При локальной нехватке показано одно неблокирующее предупреждение с разбивкой; общая нехватка показывает блокирующую ошибку и отдельные колонки `Нужно / Всего / Не хватает`. До ответа на актуальный preflight после смены склада или типа сдачи создание заблокировано, поэтому устаревший ответ не может создать поставку.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend` — зелёный.
- `python3 scripts/ui/ui_guard.py` из корня — красный только по уже затронутым другими карточками экранам: `WbProductPickerDialog.tsx`, `FfFbsOrdersScreen.tsx`, `FfFbsStockSyncScreen.tsx`, `FfFbsSupplyWorkspace.tsx`, `SellerInboundDraftScreen.tsx`. Изменённый здесь `FbsSupplyCreateDialog.tsx` отмечен как улучшение (`своя-кнопка 3 → 2`); базовая линия не менялась.
- `npm run test:unit -- FbsSupplyCreateDialog.test.ts` из frontend — не запущен: `sh: vitest: command not found`; в рабочей копии отсутствует исполняемый `frontend/node_modules/.bin/vitest`.

## Не реализовано

- Нахождение 2 из `REVIEW.md` (распределение дефицита по нескольким исходным складам и расчёт рекомендации в единицах) относится к backend-слою `fbs_supply_validator_service.py`, который не входит в файлы атома 9. Фронтенд отображает реальные строки текущего API и не подменяет складские количества.
- E2E не запускался по той же причине отсутствующей локальной установки frontend-зависимостей; сценарий обновлён под реальный верхнеуровневый ответ API.
