# Screen-dev · 07-reporting · атом 1 · rework

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/screens/ff/FfReportsPage.tsx` — сохранены контрактные ширины `130 / 110 / 110 / 100 px`; исправлены относящиеся к этому экрану находки 3 и 4 из `REVIEW.md`: смена полного среза отменяет отдельный табличный запрос, а ошибка таблицы больше не отображается как пустой отчёт и блокирует CSV с честной причиной.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/tests-e2e/ff-reports.spec.ts` — добавлен адресный сценарий `S-33-TC-008` для четырёх ширин, защиты нового среза от позднего ответа старой страницы и отдельного состояния ошибки таблицы.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/night/volna-9-recovery/cards/07-reporting/DEV.md` — обязательный отчёт текущего screen-dev прохода.

## Гейты

- ЗЕЛЁНЫЙ: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend && npx tsc --noEmit -p tsconfig.app.json` — код завершения 0, ошибок нет.
- КРАСНЫЙ вне границ `S-33`: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting && python3 scripts/ui/ui_guard.py` — для `FfReportsPage.tsx` новых нарушений нет, guard сообщает два улучшения (`своя-кнопка 1 → 0`, `своя-таблица 1 → 0`). Общий код завершения 1 дают уже существующие изменения в `frontend/src/App.tsx`, `frontend/src/components/WbProductPickerDialog.tsx`, `frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx`, `frontend/src/screens/v2/SellerInboundDraftScreen.tsx`; эти файлы не входят в слой атома и не изменялись.
- ЗЕЛЁНЫЙ: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend && npm run test:unit -- --run src/ui-kit/ReportMetricStrip.test.tsx src/ui-kit/MovementFlowChart.test.tsx src/ui-kit/States.test.tsx` — 3 файла, 7 тестов пройдены.
- ЗЕЛЁНЫЙ, проверка регистрации адресного сценария: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend && npx playwright test tests-e2e/ff-reports.spec.ts --grep "FF report keeps one table slice and distinguishes a table error from empty data" --list` — найден ровно 1 тест.
- КРАСНЫЙ по ограничению sandbox: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend && npx playwright test tests-e2e/ff-reports.spec.ts --grep "FF report keeps one table slice and distinguishes a table error from empty data" --workers=1` — Playwright не смог запустить webServer: `127.0.0.1:18000: operation not permitted`.
- ЗЕЛЁНЫЙ: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting && git diff --check` — ошибок пробелов нет.
- КРАСНЫЙ по ограничению sandbox: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting && git add -- frontend/src/screens/ff/FfReportsPage.tsx frontend/tests-e2e/ff-reports.spec.ts night/volna-9-recovery/cards/07-reporting/DEV.md && git commit -m "fix(reports): keep table slice consistent"` — Git не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-1-07-reporting1/index.lock`: `Operation not permitted`. Изменения локально реализованы, но не сохранены коммитом.

Полные backend `pytest`, `ruff check .`, `mypy .` и полный frontend-регресс не запускались: они запрещены условиями атомарной проверки этого шага.

## Не реализовано

Пункты контракта в границах атома реализованы буквально. Живая браузерная проверка добавленного сценария не выполнена только потому, что sandbox запрещает локальному webServer открыть порт `18000`; сам сценарий обнаруживается Playwright.

Находки 1, 2, 5 и 6 из `REVIEW.md` относятся к backend, общим маршрутам и blocker-документации, а не к файлу и слою этого атома; они намеренно не исправлялись.

## Находки

Секреты, ключи, токены, `.env`, кабинеты учётных данных, production `194.87.96.144` и живой кабинет Wildberries не читались и не затрагивались.
