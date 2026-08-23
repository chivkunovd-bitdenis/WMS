# Фича 1

# DEV · 05-prod-slow · атом 1

Роль: `screen-dev`.

Реализован только атом `S-03-TC-018`: существующий пользовательский E2E-сценарий теперь явно проверяет, что в состоянии `marking-print-preparing` нет кнопки «Закрыть» и любых интерактивных действий внутри карточки. Оба закрытия выполняются кликом по затемнённой области вне содержимого MUI Dialog; после повторного открытия сохранена проверка перехода в `ready` и действия «Открыть для печати».

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/frontend/tests-e2e/ff-marking-print-constructor.spec.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/night/volna-9-recovery/cards/05-prod-slow/DEV.md`

## Гейты

- Зелёный — `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/frontend && npx tsc --noEmit -p tsconfig.app.json` (exit 0).
- Красный по ранее существовавшей baseline, не по изменённому E2E-файлу — `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow && python3 scripts/ui/ui_guard.py` (exit 1). Скрипт перечислил пять монолитов вне файлов этого атома: `src/components/MarkingPrintDialog.tsx` 1687 → 1750, `src/components/WbProductPickerDialog.tsx` 0 → 646, `src/screens/v2/FfFbsOrdersScreen.tsx` 1587 → 1667, `src/screens/v2/FfFbsSupplyWorkspace.tsx` 2493 → 2498, `src/screens/v2/SellerInboundDraftScreen.tsx` 1111 → 1169. Baseline не обновлялась, запрещённые файлы не менялись.
- Красный — `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/frontend && npm run test:unit -- --related tests-e2e/ff-marking-print-constructor.spec.ts --passWithNoTests` (exit 1): установленный Vitest не поддерживает `--related`. Отдельного unit-теста для `MarkingPrintDialog` в репозитории нет; полный набор unit-тестов не запускался из-за требования атомарной проверки только относящихся к атому файлов и кейсов.
- Зелёный — `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/frontend && npx eslint tests-e2e/ff-marking-print-constructor.spec.ts` (exit 0).
- Зелёный — `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/frontend && npx playwright test tests-e2e/ff-marking-print-constructor.spec.ts --grep 'S-03 marking tape restores either of two background jobs and opens PDF explicitly' --project=chromium --list` (exit 0): обнаружен ровно один адресный тест.
- Красный из-за ограничения среды до выполнения теста — `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/frontend && npx playwright test tests-e2e/ff-marking-print-constructor.spec.ts --grep 'S-03 marking tape restores either of two background jobs and opens PDF explicitly' --project=chromium` (exit 1): Playwright webServer не смог открыть `127.0.0.1:18000`, ошибка `[Errno 1] operation not permitted`; браузерный кейс не стартовал.
- Зелёный — `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow && git diff --check -- frontend/tests-e2e/ff-marking-print-constructor.spec.ts night/volna-9-recovery/cards/05-prod-slow/DEV.md` (exit 0).
- Красный — `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow && git add -- frontend/tests-e2e/ff-marking-print-constructor.spec.ts night/volna-9-recovery/cards/05-prod-slow/DEV.md` не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-2-05-prod-slow/index.lock`: `Operation not permitted`. Коммит и push не выполнялись.

## Не реализовано

В разрешённом файле все пункты атома реализованы буквально. Не удалось подтвердить прохождение адресного браузерного теста из-за запрета среды на bind `127.0.0.1:18000`; также не получен зелёный адресный unit-гейт, потому что для этого E2E-слоя нет отдельного unit-файла, а текущий Vitest не умеет фильтр `--related`. Результат не удалось сохранить коммитом: песочница запрещает запись в Git-метаданные зарегистрированного worktree.

## Находки

Новых находок по данным, персональным данным или границам атома нет. Секреты, ключи, токены, `.env`, кабинеты учётных данных, боевой прод и живой кабинет Wildberries не читались и не затрагивались.

# Фича 2

# DEV · 05-prod-slow · атом 2

Роль: `screen-dev`.

Выполнен только атом «Убрать из карточки 05 глобальный снимок UI-инвентаря». Итоговый blob `frontend/src/ui-kit/inventory.generated.ts` совпадает с базой до первого атома карточки: промежуточная глобальная перегенерация из `7238394b` полностью отменена коммитом `bfc9ac98`, поэтому в итоговом diff карточки файл отсутствует. Генератор не запускался, данные соседних экранов не переносились и вручную не редактировались.

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/night/volna-9-recovery/cards/05-prod-slow/DEV.md`

`/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/frontend/src/ui-kit/inventory.generated.ts` проверен, но заново не изменён: его итоговый Git blob `adbdaa5e48671021ec703bf70ff088f87c78b38c` совпадает с blob в базовом коммите `d62f9afb` перед первым атомом карточки 05.

## Гейты

- Зелёный — рабочий каталог `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/frontend`, команда `npx tsc --noEmit -p tsconfig.app.json` (exit 0).
- Красный по ранее существующей baseline, не по файлам этого атома — рабочий каталог `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow`, команда `python3 scripts/ui/ui_guard.py` (exit 1). Скрипт перечислил пять монолитов вне слоя атома: `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/frontend/src/components/MarkingPrintDialog.tsx` 1687 → 1750, `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/frontend/src/components/WbProductPickerDialog.tsx` 0 → 646, `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/frontend/src/screens/v2/FfFbsOrdersScreen.tsx` 1587 → 1667, `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx` 2493 → 2498, `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/frontend/src/screens/v2/SellerInboundDraftScreen.tsx` 1111 → 1169. Baseline флагом `--update` не менялась; запрещённые соседние файлы не правились.
- Зелёный — рабочий каталог `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/frontend`, адресная команда `npm run test:unit -- src/ui-kit/TableLoadMore.test.ts`: 1 файл, 4 теста пройдены (exit 0). Полный unit-набор не запускался по правилу атомарной проверки.
- Зелёный — рабочий каталог `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow`, команда `git diff --check d62f9afb..HEAD -- frontend/src/ui-kit/inventory.generated.ts` (exit 0, вывода нет).
- Зелёный — рабочий каталог `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow`, команды `git rev-parse d62f9afb:frontend/src/ui-kit/inventory.generated.ts` и `git rev-parse HEAD:frontend/src/ui-kit/inventory.generated.ts`: обе вернули `adbdaa5e48671021ec703bf70ff088f87c78b38c`.
- Зелёный — рабочий каталог `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow`, команда `git diff --check -- night/volna-9-recovery/cards/05-prod-slow/DEV.md frontend/src/ui-kit/inventory.generated.ts` (exit 0, вывода нет).
- Красный из-за запрета записи в Git-метаданные зарегистрированного worktree — рабочий каталог `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow`, команда `git add -- night/volna-9-recovery/cards/05-prod-slow/DEV.md && git diff --cached --check -- night/volna-9-recovery/cards/05-prod-slow/DEV.md && git diff --cached --name-status && git commit -m 'night(05-prod-slow): atom 2/2 inventory boundary'` остановилась на `git add` (exit 128): не разрешено создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-2-05-prod-slow/index.lock`. Коммит с новым `DEV.md` не создан; функциональная изоляция инвентаря уже сохранена в `bfc9ac98` и присутствует в текущем `HEAD` `b66112f1`.

## Не реализовано

Все пункты атома в разрешённом слое выполнены буквально: итоговый diff карточки по UI-инвентарю пуст и не содержит данных соседних экранов, добавленных карточкой 05. Общий `ui_guard.py` остаётся красным из-за пяти ранее существующих превышений baseline вне файла и границ этого атома; исправлять эти экраны или обновлять baseline текущим контрактом запрещено. Новый отчёт `DEV.md` локально записан, но не сохранён отдельным коммитом из-за запрета среды на запись `index.lock`; восстановимый функциональный результат атома уже находится в коммите `bfc9ac98`.

## Находки

Новых находок по данным, персональным данным или границам атома нет. Секреты, ключи, токены, `.env`, кабинеты учётных данных, боевой прод и живой кабинет Wildberries не читались и не затрагивались.
