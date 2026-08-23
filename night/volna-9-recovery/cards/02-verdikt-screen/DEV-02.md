# DEV · 02-verdikt-screen · атом 2

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/frontend/tests-e2e/ff-fbs-supply.spec.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/night/volna-9-recovery/cards/02-verdikt-screen/DEV.md`

## Гейты

- Зелёный: из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/frontend` выполнено `npx tsc --noEmit -p tsconfig.app.json` (exit 0).
- Красный, не относится к этому атому: из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen` выполнено `python3 scripts/ui/ui_guard.py` (exit 1). Новые нарушения уже находятся вне разрешённого файла: `src/components/WbProductPickerDialog.tsx: экран-монолит 0 → 646` и `src/screens/v2/SellerInboundDraftScreen.tsx: экран-монолит 1111 → 1169`. Базовая линия не изменялась.
- Зелёный: из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/frontend` выполнено `npm run test:unit -- src/screens/v2/FfFbsSupplyWorkspace.test.ts` (1 файл, 3 теста passed).
- Зелёный разбор e2e без серверов: из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/frontend` выполнено `npx playwright test tests-e2e/ff-fbs-supply.spec.ts --grep 'S-03-TC-018' --list` (найден ровно 1 сценарий).
- Блокировано средой до выполнения теста: из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/frontend` выполнено `npx playwright test tests-e2e/ff-fbs-supply.spec.ts --grep 'S-03-TC-018'`; Playwright не смог поднять свой локальный API: `error while attempting to bind on address ('127.0.0.1', 18000): operation not permitted`.

## Не реализовано

Буквальный шаг «вернулся во вкладку и сразу нажал» не может быть доказан в пределах единственного разрешённого тестового файла: текущий экран обновляет открытую поставку раз в 15 секунд только при `document.visibilityState === 'visible'`, но не делает немедленный refresh по `visibilitychange`. Сценарий проверяет существующий безопасный путь: скрытая вкладка не обновляется, после возврата получает сохранённый отказ на ближайшем разрешённом refresh, затем диалог не открывается и `/deliver` не вызывается. Для буквальной немедленной проверки потребовалась бы правка `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx`, которая не входит в файлы атома 2. Полный запуск сценария также не завершён из-за запрета среды на локальный сетевой порт; продуктовый код и другие экранные файлы не менялись.

## Находки

Секреты, ключи, токены, `.env`, кабинеты учётных данных, живой Wildberries и production `194.87.96.144` не читались и не затрагивались.
