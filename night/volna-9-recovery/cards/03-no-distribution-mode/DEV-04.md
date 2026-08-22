# DEV · 03-no-distribution-mode · экран S-03 · переделка по ревью

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx` — удалено отдельное локальное состояние режима; галка и нейтральная шапка теперь читают один серверный признак `workspace.supply.boxes_without_distribution`, поэтому фоновый опрос не может показать противоречащие состояния.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/frontend/tests-e2e/ff-fbs-supply.spec.ts` — добавлен регрессионный сценарий двух внешних переключений режима через фоновое обновление workspace: `false → true` и `true → false`; он проверяет одновременно галку и текст шапки.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/night/volna-9-recovery/cards/03-no-distribution-mode/DEV.md` — отчёт роли `screen-dev`.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/frontend` — **зелёный**, exit code 0.
- `python3 scripts/ui/ui_guard.py` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode` — **красный на существующей базовой линии**: `src/components/WbProductPickerDialog.tsx` 0 → 646, `src/screens/v2/FfFbsSupplyWorkspace.tsx` 2493 → 2505, `src/screens/v2/SellerInboundDraftScreen.tsx` 1111 → 1169. Базовая линия не обновлялась. До этой переделки `FfFbsSupplyWorkspace.tsx` уже имел 2507 строк; текущая правка уменьшила его до 2505 и не добавила новое превышение.
- `npm run test:unit` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/frontend` — **зелёный**: 19 файлов, 138 тестов прошли.
- `npx eslint tests-e2e/ff-fbs-supply.spec.ts` — **зелёный**, exit code 0.
- `npx playwright test --list tests-e2e/ff-fbs-supply.spec.ts --grep 'boxes without distribution follows (assigned orders|background refresh)'` — **зелёный**: оба целевых сценария обнаружены и загружаются Playwright без ошибок компиляции.
- `npx playwright test tests-e2e/ff-fbs-supply.spec.ts --grep 'boxes without distribution follows (assigned orders|background refresh)'` — **не запущен до браузерного шага**: Playwright webServer не смог привязать локальный API к `127.0.0.1:18000`, `operation not permitted`. Это ограничение среды; продуктовый сценарий в живом браузере здесь не подтверждён.

## Не реализовано

- Живой браузерный прогон названных сценариев не выполнен, потому что среда запретила запуск локального API на порту `18000`.
- Находка 1 из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/night/volna-9-recovery/cards/03-no-distribution-mode/REVIEW.md` относится к backend-сервису предыдущего атома и не входит в роль `screen-dev`; этот слой не менялся.
- Буквальный `tasks/<slug>/CONTRACT.md` в рабочей копии отсутствует. Переделка выполнена по явно заданному атому 4 из `FEATURES.md` и экранной находке 2 из `REVIEW.md`; новые продуктовые решения не добавлялись.

## Находки

- Секреты, ключи, токены, `.env` и кабинеты учётных данных не читались.
- Отдельный Git-коммит создать не удалось: Git не может создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-3-03-no-distribution-mode1/index.lock` и завершает `git add` с `Operation not permitted`. Изменения остаются только в постоянной рабочей копии; проверенного commit SHA для этой переделки нет. Чужое изменение `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/night/volna-9-recovery/JOURNAL.md` не добавлялось и не редактировалось.
