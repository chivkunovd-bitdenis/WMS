# DEV · 07-reporting · атом 11 · повторный проход screen-dev

Атом 11 повторно сверен с `CONTRACT.md`, `FEATURES.md`, `MOCKUP.html`, `ARCH-CROSS.md` и актуальным `REVIEW.md`. Все три находки review уже присутствуют исправленными в текущей именованной ветке и были проверены по фактическому коду и тестам: retry сводки не отменяет медленный табличный запрос, MUI-свойства `MovementFlowChart` совместимы с TypeScript, а Vitest обнаруживает `.test.tsx`-спецификации. Дополнительной продуктовой логики и соседних экранов этот проход не менял.

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/night/volna-9-recovery/cards/07-reporting/DEV.md` — записан обязательный артефакт повторного прохода.

Проверенные исправления review уже сохранены в текущей ветке в следующих файлах и не потребовали нового diff в этом проходе:

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/screens/ff/FfReportsPage.tsx` — отдельный `overviewRetryAbortRef` сохраняет выполняющийся табличный запрос при повторе сводки.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/tests-e2e/ff-reports.spec.ts` — сценарий `S-33-TC-012` удерживает таблицу в загрузке до успешного retry и затем проверяет её появление без повторного inventory-запроса; здесь же проверяются обе группировки, вторая страница, неизменность верхней сводки, причина недоступности CSV и MIME `text/csv`.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/tests-e2e/seller-reports.spec.ts` — seller-регрессия общего экрана.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/ui-kit/MovementFlowChart.tsx` — проблемные `alignItems`, `fontWeight` и `flexWrap` передаются через `sx`.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/vitest.config.ts` — маска включает `src/**/*.test.tsx`.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/apps/seller/SellerApp.test.tsx`, `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/ui-kit/MovementFlowChart.test.tsx`, `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/ui-kit/ReportMetricStrip.test.tsx`, `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/ui-kit/States.test.tsx` — ранее пропущенные целевые unit-тесты теперь обнаруживаются и проходят.

## Гейты

- **ЗЕЛЁНЫЙ:** `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend && npx tsc --noEmit -p tsconfig.app.json` — TypeScript завершился с кодом 0 без ошибок.
- **КРАСНЫЙ только вне файлов S-33:** `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting && python3 scripts/ui/ui_guard.py` — прежние превышения храповика находятся в `frontend/src/App.tsx`, `frontend/src/components/WbProductPickerDialog.tsx`, `frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx` и `frontend/src/screens/v2/SellerInboundDraftScreen.tsx`. Для `frontend/src/screens/ff/FfReportsPage.tsx` проверка сообщает улучшения `своя-кнопка 1 → 0` и `своя-таблица 1 → 0`. Baseline не изменялась.
- **ЗЕЛЁНЫЙ, целевые тесты review:** `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend && npx vitest run src/apps/seller/SellerApp.test.tsx src/ui-kit/MovementFlowChart.test.tsx src/ui-kit/ReportMetricStrip.test.tsx src/ui-kit/States.test.tsx` — 4 файла, 9 тестов пройдены.
- **ЗЕЛЁНЫЙ:** `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend && npm run test:unit` — 23 файла, 147 тестов пройдены; все четыре `.test.tsx`-спецификации из review вошли в прогон.
- **КРАСНЫЙ из-за запрета ОС на локальный порт, браузерные кейсы не начались:** `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend && npx playwright test tests-e2e/ff-reports.spec.ts tests-e2e/seller-reports.spec.ts --reporter=line` — webServer не смог привязаться к `127.0.0.1:18000`, ошибка `[Errno 1] operation not permitted`.
- **ЗЕЛЁНЫЙ, обнаружение атомарных Playwright-сценариев:** `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend && npx playwright test tests-e2e/ff-reports.spec.ts tests-e2e/seller-reports.spec.ts --list` — обнаружено 5 тестов в 2 файлах.
- **ЗЕЛЁНЫЙ:** `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend && npx eslint src/screens/ff/FfReportsPage.tsx src/ui-kit/MovementFlowChart.tsx src/apps/seller/SellerApp.test.tsx src/ui-kit/MovementFlowChart.test.tsx src/ui-kit/ReportMetricStrip.test.tsx src/ui-kit/States.test.tsx tests-e2e/ff-reports.spec.ts tests-e2e/seller-reports.spec.ts`.
- **КРАСНЫЙ из-за запрета записи в общий Git-каталог:** `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting && git add -- night/volna-9-recovery/cards/07-reporting/DEV.md && git diff --cached --check && git diff --cached --stat && git commit -m "docs(reports): record atom 11 review verification"` — Git не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-1-07-reporting1/index.lock`, ошибка `Operation not permitted`. Изменённый оркестратором `night/volna-9-recovery/JOURNAL.md` не добавлялся.

Полные backend `pytest`, `ruff check .` и `mypy .` не запускались: атомарная проверка прямо запрещает их на этом шаге.

## Не реализовано

- Кодовые пункты контракта атома 11 и все три находки повторного review присутствуют в ветке буквально; известных отступлений в разрешённом экранном слое нет.
- Живой Playwright-прогон не состоялся из-за системного запрета на привязку локального порта. Поэтому браузерные сценарии не объявляются зелёными, хотя их обнаружение, TypeScript, ESLint и относящиеся unit-тесты прошли.
- Общий `ui_guard.py` остаётся красным из-за четырёх чужих файлов вне разрешённой границы экрана S-33; исправлять их «заодно» и обновлять baseline роль `screen-dev` не имеет права.
- Артефакт локально записан, но отдельный Git-коммит этого прохода создать невозможно из-за запрета sandbox на запись в общий Git-каталог worktree. Проверенного нового commit SHA нет; уже существующие кодовые исправления восстанавливаются из текущего `HEAD` `804eea99a59544477e38ffbf6105dfa871328100`.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных, production `194.87.96.144` и живой кабинет Wildberries не читались и не затрагивались.
