# Фича 1

# Screen-dev · 07-reporting · атом 1

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/night/volna-9-recovery/cards/07-reporting/DEV.md` — обязательный артефакт этого повторного прохода.

Реализация атома уже сохранена в текущем `HEAD` commit `d610b961`: в `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/screens/ff/FfReportsPage.tsx` для товарной группировки явно указаны ширины колонок `balance: 130`, `in: 110`, `out: 110`, `net: 100`. Повторная правка кода не требовалась и не выполнялась.

## Гейты

- ЗЕЛЁНЫЙ: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend && npx tsc --noEmit -p tsconfig.app.json` — завершилась с кодом 0, без ошибок.
- КРАСНЫЙ вне границы атома: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting && python3 scripts/ui/ui_guard.py` — новые нарушения только в `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/App.tsx`, `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/components/WbProductPickerDialog.tsx`, `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx` и `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/screens/v2/SellerInboundDraftScreen.tsx`. Для `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/screens/ff/FfReportsPage.tsx` guard сообщает только улучшения «своя-кнопка 1 → 0» и «своя-таблица 1 → 0»; baseline не изменялась.
- ЗЕЛЁНЫЙ: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend && npm run test:unit -- --run src/ui-kit/ReportMetricStrip.test.tsx src/ui-kit/MovementFlowChart.test.tsx src/ui-kit/States.test.tsx` — 3 файла, 7 тестов пройдены.

Полные backend `pytest`, `ruff check .` и `mypy .` не запускались: они прямо запрещены атомарной проверкой этого шага.

## Не реализовано

Для первого атома нет невыполненных пунктов контракта: четыре ширины заданы буквально.

Находка R-31 из `DESIGN-REVIEW.md` намеренно не менялась: она является самостоятельным вторым атомом в `FEATURES.md`, а пользователь поручил реализовать только первый.

## Находки

Секреты, ключи, токены, `.env`, кабинеты учётных данных, production `194.87.96.144` и живой кабинет Wildberries не читались и не затрагивались.

# Фича 2

# DEV · 07-reporting · атом 2

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/screens/ff/FfReportsPage.tsx` — проверена реализация атома: пагинация использует `SecondaryAction`, то есть MUI `Button` с `variant="outlined"`; сохранены `data-testid` и `disabledReason`. Изменение уже содержится в commit `d610b961165a47a3c8706b59c5c52f26ea825b84`.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/night/volna-9-recovery/cards/07-reporting/DEV.md` — артефакт данного шага.

## Гейты

- ЗЕЛЁНЫЙ: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend && npx tsc --noEmit -p tsconfig.app.json`.
- КРАСНЫЙ вне границ атома: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting && python3 scripts/ui/ui_guard.py`. Новые нарушения только в `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/App.tsx`, `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/components/WbProductPickerDialog.tsx`, `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx` и `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/screens/v2/SellerInboundDraftScreen.tsx`; их менять запрещено границей S-33. Для `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/screens/ff/FfReportsPage.tsx` guard сообщает улучшение: «своя-кнопка 1 → 0».
- ЗЕЛЁНЫЙ, адресный запуск: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend && npm run test:unit -- --passWithNoTests src/screens/ff/FfReportsPage.test.tsx`. У экрана нет unit-файла, поэтому Vitest завершился с `No test files found, exiting with code 0`; посторонние unit-тесты не запускались согласно правилу атомарной проверки.
- КРАСНЫЙ по ограничению sandbox: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend && npx playwright test tests-e2e/ff-reports.spec.ts --grep "FF reports: section opens and shows movement summary for a product with intake" --workers=1`. Playwright не смог запустить webServer: `127.0.0.1:18000: operation not permitted`.

## Не реализовано

- Нет. Атом 2 уже реализован буквально: «Скачать CSV» остаётся `PrimaryAction`, а «Назад» и «Вперёд» — outlined `SecondaryAction` с неизменными `data-testid` и подсказками недоступности.
