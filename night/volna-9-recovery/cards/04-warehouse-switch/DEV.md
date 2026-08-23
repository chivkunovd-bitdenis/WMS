# DEV · 04-warehouse-switch · атом 1

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/docs/blockers/S-14.md`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/night/volna-9-recovery/cards/04-warehouse-switch/DEV.md`

Создана запись B-01 для S-14 со всеми шестью обязательными полями. Она сверяет
точное экранное условие `selected !== null`, no-op для `onWarehouseChange` и
сообщение `Склад закреплён: открыто задание упаковки` с серверной границей: у
созданного задания упаковки отсутствует маршрут `PATCH`/`PUT` смены
`warehouse_id`, а операции адресуются по `task_id`.

`/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/ff/FfPackagingPage.tsx`
не менялся: он остаётся источником уже принятого условия, как требует атом.

## Гейты

- Зелёный: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend && npx tsc --noEmit -p tsconfig.app.json` — код возврата 0.
- Красный вне файлов и слоя атома: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch && python3 scripts/ui/ui_guard.py` — новые нарушения в чужих файлах `frontend/src/components/WbProductPickerDialog.tsx`, `frontend/src/screens/v2/FfFbsOrdersScreen.tsx`, `frontend/src/screens/v2/FfFbsStockSyncScreen.tsx`, `frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx`, `frontend/src/screens/v2/SellerInboundDraftScreen.tsx`. Для S-14 guard сообщает улучшение `frontend/src/screens/ff/FfPackagingPage.tsx: экран-монолит 2146 → 2143`; базовая линия не менялась.
- Не завершился: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend && npm run test:unit -- src/screens/ff/FfPackagingPage.test.ts -t 'S-14-TC-001|S-14-TC-002'`. Vitest начал collection (`RUN v3.2.6`), за 60 секунд не вывел кейсов и был остановлен Ctrl-C с кодом 130. Запуск ограничен ровно назначенными регрессиями S-14-TC-001 и S-14-TC-002; полный unit- и backend-регресс не запускались по ограничению атома.
- Не сохранено в Git: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch && git add docs/blockers/S-14.md night/volna-9-recovery/cards/04-warehouse-switch/DEV.md && git diff --cached --check && git commit -m "docs(packaging): record locked task warehouse"` не начал индексацию: Git не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-1-04-warehouse-switch/index.lock` (`Operation not permitted`). Индекс не изменён.

## Не реализовано

Нет. Реализован только атом 1 из `FEATURES.md`: реестр блокировки S-14. Экран,
API и модель намеренно не менялись, поскольку поведение уже принято и не входит в
документационный объём атома.

## Находки

`ui_guard.py` не проходит из-за новых нарушений в пяти чужих файлах. Секреты,
ключи, токены, `.env`, кабинеты учётных данных, живой Wildberries и production
`194.87.96.144` не открывались и не изменялись.
