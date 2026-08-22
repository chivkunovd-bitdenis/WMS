# DEV · 03-no-distribution-mode · атом 4 · переделка по ревью

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx` — добавлена версия мутаций workspace: успешное переключение режима инвалидирует фоновые GET-запросы, начатые до операции или во время неё, поэтому их поздний ответ больше не откатывает галку и нейтральную шапку. Итоговое число строк файла не выросло относительно текущего `HEAD` (2504 строки до и после правки).
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/frontend/tests-e2e/ff-fbs-supply.spec.ts` — прежняя последовательная проверка фонового обновления заменена регрессией из ревью: старый GET фиксирует снимок `false` и задерживается, POST успешно возвращает `true`, затем старый GET освобождается; тест проверяет, что режим и нейтральная шапка остаются включёнными.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/night/volna-9-recovery/cards/03-no-distribution-mode/DEV.md` — отчёт роли `screen-dev`.

## Гейты

- Из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/frontend`: `npx tsc --noEmit -p tsconfig.app.json` — **зелёный**, exit code 0.
- Из корня: `python3 scripts/ui/ui_guard.py` — **красный на существующей базовой линии**, exit code 1: `src/components/WbProductPickerDialog.tsx` 0 → 646, `src/screens/v2/FfFbsSupplyWorkspace.tsx` 2493 → 2505, `src/screens/v2/SellerInboundDraftScreen.tsx` 1111 → 1169. Базовая линия не обновлялась, чужие экраны не трогались; затронутый `FfFbsSupplyWorkspace.tsx` содержит 2504 физические строки и не вырос относительно текущего `HEAD`.
- Из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/frontend`: `npm run test:unit -- --run src/screens/v2/fbsApi.test.ts` — **зелёный**, 1 файл, 5 тестов прошли.
- Из того же каталога: `npx eslint tests-e2e/ff-fbs-supply.spec.ts` — **зелёный**, exit code 0.
- Из того же каталога: `npx playwright test --list tests-e2e/ff-fbs-supply.spec.ts --grep 'boxes without distribution (follows assigned orders|ignores stale background refresh after toggle)'` — **зелёный**, оба целевых сценария найдены и компилируются.
- Из того же каталога: `npx playwright test tests-e2e/ff-fbs-supply.spec.ts --grep 'boxes without distribution (follows assigned orders|ignores stale background refresh after toggle)'` — **красный до запуска браузерных кейсов**: локальный API не смог привязаться к `127.0.0.1:18000`, `operation not permitted`; Playwright завершился с exit code 1.
- Из корня: `git diff --check` — **зелёный**, exit code 0.

## Не реализовано

- Живой браузерный прогон двух названных сценариев не выполнен: среда запретила Playwright webServer открыть локальный порт `18000`. Сами сценарии обнаруживаются и проходят загрузку/компиляцию через `playwright test --list`.
- Находки 1 и 2 из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/night/volna-9-recovery/cards/03-no-distribution-mode/REVIEW.md` относятся к backend-слою предыдущего атома и не входят в роль `screen-dev`; в текущем `HEAD` они уже сохранены отдельным коммитом `c1cb8e58` и в этом проходе не менялись.
- Буквальный `tasks/<slug>/CONTRACT.md` в рабочей копии отсутствует. Переделка выполнена строго по атому 4 из `FEATURES.md`, экранной находке 3 из `REVIEW.md` и экрану S-03 из `frontend/screens.registry.json`; новых продуктовых решений не добавлено.

## Находки

- Секреты, ключи, токены, `.env` и кабинеты учётных данных не читались.

## Блокеры

- Изменения локально записаны в постоянной рабочей копии, но отдельный Git-коммит создать невозможно: `git add -- frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx frontend/tests-e2e/ff-fbs-supply.spec.ts night/volna-9-recovery/cards/03-no-distribution-mode/DEV.md` завершился ошибкой `Unable to create '/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-3-03-no-distribution-mode1/index.lock': Operation not permitted`. Текущий `HEAD` — `c1cb8e58`; он не содержит экранную переделку этого прохода. Несвязанное изменение `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/night/volna-9-recovery/JOURNAL.md` не редактировалось и не индексировалось этой ролью.
