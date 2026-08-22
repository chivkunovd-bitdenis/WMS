# DEV · 07-reporting · атом 10 · переделка по повторному review

Исправлена гонка частичного отказа сводки: повторный запрос `/reports/overview` теперь использует собственный `AbortController` и не отменяет медленный запрос будущей таблицы, запущенный общей загрузкой фильтра. При смене фильтра старый retry по-прежнему отменяется, поэтому ответ от прежнего среза не может попасть в новый.

Сценарий `S-33-TC-012` усилен: mock таблицы намеренно остаётся незавершённым после первого `503` сводки, оператор нажимает «Повторить», успешный повтор сводки завершается, затем отпускается исходный табличный запрос. Тест требует, чтобы таблица закончила загрузку без второго запроса.

Две остальные находки повторного review уже находились в текущем `HEAD` до этого прохода и подтверждены гейтами: `MovementFlowChart` передаёт несовместимые с MUI свойства через `sx`, а `vitest.config.ts` включает `src/**/*.test.tsx`. Целевой unit-прогон действительно обнаружил четыре `.test.tsx`-файла и выполнил 9 тестов.

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/screens/ff/FfReportsPage.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/tests-e2e/ff-reports.spec.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/night/volna-9-recovery/cards/07-reporting/DEV.md`

`/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/tests-e2e/seller-reports.spec.ts` не менялся: требуемая seller-регрессия уже проверяет отсутствие фильтра селлера, служебного склада и технического предупреждения.

## Гейты

- **ЗЕЛЁНЫЙ:** `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend && npx tsc --noEmit -p tsconfig.app.json`.
- **КРАСНЫЙ вне файлов атома:** `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting && python3 scripts/ui/ui_guard.py`. Храповик сообщил прежние превышения baseline только в `frontend/src/App.tsx`, `frontend/src/components/WbProductPickerDialog.tsx`, `frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx` и `frontend/src/screens/v2/SellerInboundDraftScreen.tsx`; по `FfReportsPage.tsx` показаны улучшения «своя-кнопка 1 → 0» и «своя-таблица 1 → 0». Baseline не менялась.
- **ЗЕЛЁНЫЙ:** `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend && npm run test:unit -- src/apps/seller/SellerApp.test.tsx src/ui-kit/MovementFlowChart.test.tsx src/ui-kit/ReportMetricStrip.test.tsx src/ui-kit/States.test.tsx` — 4 файла, 9 тестов пройдены.
- **ЗЕЛЁНЫЙ:** `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend && npx eslint src/screens/ff/FfReportsPage.tsx tests-e2e/ff-reports.spec.ts tests-e2e/seller-reports.spec.ts src/ui-kit/MovementFlowChart.tsx src/apps/seller/SellerApp.test.tsx src/ui-kit/MovementFlowChart.test.tsx src/ui-kit/ReportMetricStrip.test.tsx src/ui-kit/States.test.tsx vitest.config.ts`.
- **КРАСНЫЙ по ограничению среды до начала browser-кейсов:** `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend && npx playwright test tests-e2e/ff-reports.spec.ts tests-e2e/seller-reports.spec.ts --reporter=line` — API webServer не смог привязаться к `127.0.0.1:18000`, ОС вернула `operation not permitted`; production и живой кабинет Wildberries не затрагивались.
- **ЗЕЛЁНЫЙ, разбор целевых spec:** `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend && npx playwright test tests-e2e/ff-reports.spec.ts tests-e2e/seller-reports.spec.ts --list` — Playwright обнаружил 5 тестов в 2 файлах, включая усиленный retry-кейс и seller-регрессию.
- **ЗЕЛЁНЫЙ:** `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend && git diff --check`.
- **КРАСНЫЙ по ограничению Git-каталога:** `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting && git add -- frontend/src/screens/ff/FfReportsPage.tsx frontend/tests-e2e/ff-reports.spec.ts night/volna-9-recovery/cards/07-reporting/DEV.md && git diff --cached --check && git diff --cached --stat && git commit -m "fix(reports): preserve table during summary retry"` — Git не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-1-07-reporting1/index.lock`: `Operation not permitted`. Чужой `night/volna-9-recovery/JOURNAL.md` не добавлялся.

Полные backend `pytest`, `ruff check .` и `mypy .` не запускались в соответствии с атомарной границей.

## Не реализовано

- Буквально подтвердить усиленный `S-33-TC-012` и seller-регрессию живым Playwright не удалось: локальный API запрещено поднимать системной политикой sandbox. Spec изменён, TypeScript и ESLint зелёные, но это не заменяет browser-прогон.
- `ui_guard.py` нельзя сделать зелёным в границах атома: четыре превышения находятся в чужих файлах и не связаны с текущим diff. Базовая линия не обновлялась.
- Ремонт локально реализован, но не сохранён отдельным Git-коммитом: sandbox разрешает запись в рабочую копию, но запрещает запись в общий Git-каталог зарегистрированного worktree. Проверенного commit SHA для этого прохода нет.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных, production `194.87.96.144` и живой кабинет Wildberries не читались и не затрагивались.
