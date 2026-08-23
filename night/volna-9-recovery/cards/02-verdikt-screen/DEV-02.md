# DEV · 02-verdikt-screen · атом 2

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx` — при возврате вкладки сразу запрашивает workspace и закрывает «Передать в WB» до свежего ответа; повторный опрос в 15 секунд сохранён.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/frontend/tests-e2e/ff-fbs-supply.spec.ts` — `S-03-TC-018` удерживает refresh после `visibilitychange`, делает обычную попытку клика без `force`, затем проверяет отсутствие диалога и `/deliver` до отказа WB; `S-03-TC-019` назван как относящаяся регрессия.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/night/volna-9-recovery/cards/02-verdikt-screen/DEV.md` — отчёт атома.

## Гейты

- Зелёный: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/frontend && npx tsc --noEmit -p tsconfig.app.json`.
- Зелёный: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/frontend && npm run test:unit -- src/screens/v2/FfFbsSupplyWorkspace.test.ts` — 1 файл, 3 теста passed.
- Красный вне файлов атома: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen && python3 scripts/ui/ui_guard.py` сообщает только `src/components/WbProductPickerDialog.tsx: экран-монолит 0 → 646` и `src/screens/v2/SellerInboundDraftScreen.tsx: экран-монолит 1111 → 1169`. Нарушения в `FfFbsSupplyWorkspace.tsx` нет; базовая линия не менялась.
- Зелёный: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/frontend && npx playwright test tests-e2e/ff-fbs-supply.spec.ts --grep 'S-03-TC-018|S-03-TC-019' --list` — найдены ровно 2 сценария.
- Заблокировано средой: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/frontend && npx playwright test tests-e2e/ff-fbs-supply.spec.ts --grep 'S-03-TC-018|S-03-TC-019'` не стартует, потому что Playwright не может привязать локальный API к `127.0.0.1:18000` (`operation not permitted`).

## Не реализовано

- Нет. Реализован только атом 2 из `FEATURES.md`; атомы 1 и следующие не изменялись в этой работе.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных, живой Wildberries и production `194.87.96.144` не читались и не затрагивались.
- Сохранение в Git заблокировано средой: `git add frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx frontend/tests-e2e/ff-fbs-supply.spec.ts night/volna-9-recovery/cards/02-verdikt-screen/DEV.md` не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-2-02-verdikt-screen1/index.lock` (`Operation not permitted`), поэтому отдельного commit SHA нет.
