# DEV · 05-prod-slow · повторный проход screen-dev · атом 1

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/frontend/src/ui-kit/inventory.generated.ts` — убрана глобальная перегенерация UI-инвентаря, впервые попавшая в исходный коммит атома 1; файл возвращён к состоянию до карточки `05-prod-slow`, потому что контракт не требует нового или изменённого UI-kit.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/night/volna-9-recovery/cards/05-prod-slow/DEV.md` — записан этот обязательный артефакт повторного прохода.

Файлы реализации атома уже содержали подтверждённый ревьюером результат и в этом
повторном проходе не переписывались:

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/frontend/src/screens/v2/FfFbsOrdersScreen.tsx` — таблица вкладки «Новые» использует `tableLayout: 'fixed'`, ширину 713 px и четыре заголовка шириной 210 / 135 / 180 / 140 px с `whiteSpace: 'nowrap'`.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/frontend/tests-e2e/ff-fbs-orders.spec.ts` — сценарий S-03-TC-016 проверяет фиксированную раскладку, ширину таблицы, фактические ширины и однострочность четырёх заголовков.

## Гейты

- Зелёный: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/frontend && npx tsc --noEmit -p tsconfig.app.json` — код возврата 0, ошибок нет.
- Зелёный: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/frontend && npm run test:unit -- src/screens/v2/fbsApi.test.ts` — 1 файл, 5 тестов прошли.
- Красный на существующих превышениях baseline: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow && python3 scripts/ui/ui_guard.py`. Вывод: `MarkingPrintDialog.tsx` 1687 → 1750, `WbProductPickerDialog.tsx` 0 → 646, `FfFbsOrdersScreen.tsx` 1587 → 1667, `FfFbsSupplyWorkspace.tsx` 2493 → 2498, `SellerInboundDraftScreen.tsx` 1111 → 1169. Флаг `--update` не применялся.
- Не дошёл до выполнения теста из-за ограничения среды: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/frontend && npx playwright test tests-e2e/ff-fbs-orders.spec.ts --grep 'fbs orders: search keeps list, selected drawer stays stable and Excel downloads'`. Playwright webServer получил `operation not permitted` при попытке bind `127.0.0.1:18000`.

## Не реализовано

- Пункты контракта текущего атома реализованы буквально; ревью уже подтвердило фиксированную раскладку и адресные E2E-ожидания.
- Находка `REVIEW.md` по `frontend/tests-e2e/ff-marking-print-constructor.spec.ts` не исправлялась: она относится к отдельному атому 3 (`TapePreparationStatus`, S-03-TC-018), тогда как текущий запуск жёстко ограничен атомом 1 — заголовками таблицы «Новые».
- Полный браузерный прогон не подтверждён из-за запрета среды на открытие локального порта, указанного выше.

Секреты, ключи, токены, `.env`, кабинеты учётных данных, боевой прод и живой
кабинет Wildberries не читались и не затрагивались.
