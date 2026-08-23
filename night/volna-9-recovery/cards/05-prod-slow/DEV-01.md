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
