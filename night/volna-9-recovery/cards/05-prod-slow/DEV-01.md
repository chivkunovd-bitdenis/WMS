# DEV · 05-prod-slow · ремонт S-03-TC-018

Роль: `screen-dev`.

Локально реализован только назначенный атом: в первом цикле состояния `marking-print-preparing` сценарий отправляет `Escape` и проверяет скрытие `marking-print-dialog`; после повторного открытия сохраняет проверки отсутствия кнопки «Закрыть» и любых интерактивных действий, затем отдельно закрывает диалог кликом по backdrop и снова проверяет скрытие. Реализация `MarkingPrintDialog` и остальные части карточки не менялись.

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/frontend/tests-e2e/ff-marking-print-constructor.spec.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/night/volna-9-recovery/cards/05-prod-slow/DEV.md`

## Гейты

- Зелёный — рабочий каталог `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/frontend`, команда `npx tsc --noEmit -p tsconfig.app.json` (exit 0).
- Красный по ранее существующей baseline, не по изменённому E2E-файлу — рабочий каталог `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow`, команда `python3 scripts/ui/ui_guard.py` (exit 1). Скрипт перечислил пять монолитов вне файлов этого атома: `frontend/src/components/MarkingPrintDialog.tsx` 1687 → 1750, `frontend/src/components/WbProductPickerDialog.tsx` 0 → 646, `frontend/src/screens/v2/FfFbsOrdersScreen.tsx` 1587 → 1667, `frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx` 2493 → 2498, `frontend/src/screens/v2/SellerInboundDraftScreen.tsx` 1111 → 1169. Baseline флагом `--update` не менялась; эти запрещённые контрактом файлы не правились.
- Зелёный — рабочий каталог `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/frontend`, адресная команда `npm run test:unit -- src/utils/markingPrintPresets.test.ts`: 1 файл, 4 теста пройдены (exit 0). Полный unit-набор не запускался по правилу атомарной проверки.
- Зелёный — рабочий каталог `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/frontend`, команда `npx eslint tests-e2e/ff-marking-print-constructor.spec.ts` (exit 0).
- Зелёный — рабочий каталог `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/frontend`, команда `npx playwright test tests-e2e/ff-marking-print-constructor.spec.ts --grep 'S-03 marking tape restores either of two background jobs and opens PDF explicitly' --project=chromium --list`: найден ровно 1 тест в 1 файле (exit 0).
- Красный из-за ограничения среды до выполнения теста — рабочий каталог `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/frontend`, команда `npx playwright test tests-e2e/ff-marking-print-constructor.spec.ts --grep 'S-03 marking tape restores either of two background jobs and opens PDF explicitly' --project=chromium` (exit 1). Playwright webServer не смог открыть `127.0.0.1:18000`: `[Errno 1] operation not permitted`; браузер и сам кейс не стартовали.
- Зелёный — рабочий каталог `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow`, команда `git diff --check -- frontend/tests-e2e/ff-marking-print-constructor.spec.ts night/volna-9-recovery/cards/05-prod-slow/DEV.md` (exit 0).
- Красный из-за запрета записи в Git-метаданные зарегистрированного worktree — рабочий каталог `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow`, команда `git add -- frontend/tests-e2e/ff-marking-print-constructor.spec.ts night/volna-9-recovery/cards/05-prod-slow/DEV.md && git diff --cached --check && git diff --cached --name-status && git commit -m 'test(05-prod-slow): restore Esc preparation coverage'` остановилась на `git add` (exit 128): не удалось создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-2-05-prod-slow/index.lock`, `Operation not permitted`. Коммит и push не выполнены.

## Не реализовано

Все пункты разрешённого тестового атома реализованы буквально. Не удалось подтвердить исполнение `S-03-TC-018` в браузере из-за запрета среды на bind `127.0.0.1:18000`. Общий `ui_guard.py` остаётся красным на пяти ранее существующих превышениях baseline вне разрешённого файла; исправлять эти компоненты или обновлять baseline текущим контрактом запрещено. Локальный результат не сохранён отдельным коммитом, потому что песочница не разрешает запись Git `index.lock` зарегистрированного worktree.

## Находки

Новых находок по данным, персональным данным или границам атома нет. Секреты, ключи, токены, `.env`, кабинеты учётных данных, боевой прод `194.87.96.144` и живой кабинет Wildberries не читались и не затрагивались.
