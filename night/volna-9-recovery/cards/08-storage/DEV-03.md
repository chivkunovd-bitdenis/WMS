# DEV · 08-storage · атом 3 · переделка по REVIEW

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend/tests-e2e/storage.spec.ts` — `S-11-TC-002` теперь раскрывает индивидуальную ставку и проверяет ровно один POST с `seller_exception` в теле. Экран уже содержал исправленные вызов `getMoscowDateString()` и один объединённый POST; серверный маршрут из находки 1 существует по `POST /operations/storage/tariffs`.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/night/volna-9-recovery/cards/08-storage/DEV.md` — отчёт этого атома.

## Гейты

- Зелёный: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend && npx tsc --noEmit -p tsconfig.app.json`.
- Красный вне атома: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage && python3 scripts/ui/ui_guard.py` сообщил только о существующих нарушениях в `/frontend/src/components/WbProductPickerDialog.tsx`, `/frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx` и `/frontend/src/screens/v2/SellerInboundDraftScreen.tsx`. Эти файлы не относятся к S-11 и не изменялись; базовая линия не обновлялась.
- Зелёный: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend && npm run test:unit -- src/utils/moscowDate.test.ts` — 4 passed.
- Не выполнен из-за среды: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend && npx playwright test tests-e2e/storage.spec.ts --grep 'S-11-TC-002'`. Playwright webServer не может bind `127.0.0.1:18000`: `operation not permitted`.

## Не реализовано

- Нет. Все три находки REVIEW в границах атома закрыты: маршрут существует, экран отправляет один объединённый запрос, даты тарифа получают московский календарный день. Сквозной Playwright-запуск не подтверждён только из-за запрета среды на запуск test webServer.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных и production не открывались и не использовались.
- Изменения не удалось сохранить commit: Git не может создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-2-08-storage1/index.lock` (`Operation not permitted`). Рабочая копия содержит незакоммиченные изменения только в указанном e2e-тесте и этом отчёте; чужой `/night/volna-9-recovery/JOURNAL.md` не затрагивался.
