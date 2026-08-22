# DEV · 04-warehouse-switch · screen-dev · feature 13

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/SellerInboundDraftScreen.tsx` — добавлена защита seller-портала от отображения служебных складов `FBS WB *`; выбор и подпись используют только доступные операционные склады.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/sellerInboundDocumentUi.test.ts` — добавлена проверка, что служебный склад не попадает в варианты селлера.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/night/volna-9-recovery/cards/04-warehouse-switch/DEV.md` — этот отчёт.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend` — не завершён: процесс не вывел результат и был остановлен после ожидания; ошибок TypeScript в выводе нет.
- `python3 scripts/ui/ui_guard.py` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch` — красный: зафиксирован рост монолита `SellerInboundDraftScreen.tsx` `1111 → 1251`, а также ранее существующие/чужие для этого атома нарушения в `WbProductPickerDialog.tsx`, `FfFbsOrdersScreen.tsx`, `FfFbsStockSyncScreen.tsx`, `FfFbsSupplyWorkspace.tsx`. Baseline не обновлялся.
- `npm run test:unit -- --run src/screens/v2/sellerInboundDocumentUi.test.ts` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend` — красный до запуска теста: `vitest: command not found`.

## Не реализовано

- Полный browser-сценарий с двумя операционными складами не запускался: локальный test runner не установлен (`vitest` отсутствует), а успешная browser-проверка требует доступного backend/e2e окружения. Основная логика выбора и сохранения черновика уже присутствовала в предыдущем атоме и не менялась.
- Находок про секреты, ключи, токены, `.env`, кабинеты учётных данных или боевой прод нет: такие материалы не открывались.
