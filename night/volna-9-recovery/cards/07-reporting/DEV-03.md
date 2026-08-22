# Screen-dev report · 07-reporting · атом 3

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/vitest.config.ts` — добавлено обнаружение `src/**/*.test.tsx`, чтобы существующий атомарный тест `WarningNotice` действительно запускался.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/night/volna-9-recovery/cards/07-reporting/DEV.md` — записан отчёт повторного прохода.

Реализация атома уже находится в разрешённых файлах `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/ui-kit/States.tsx`, `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/ui-kit/index.ts` и `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/ui-kit/States.test.tsx`; менять её для закрытия находки review не потребовалось. `WarningNotice` использует MUI `Alert` с `severity="warning"`, совпадающий с `ErrorNotice` отступ `mb: 2`, принимает `testId` и экспортируется через публичный индекс ui-kit.

## Гейты

- **ЗЕЛЁНЫЙ:** `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend && npm run test:unit -- --run src/ui-kit/States.test.tsx` — Vitest обнаружил `src/ui-kit/States.test.tsx`; 1 файл и 1 тест пройдены. Тест проверяет `data-testid`, доступную роль `alert`, warning-класс MUI и читаемый текст.
- **КРАСНЫЙ вне границы атома 3:** `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend && npx tsc --noEmit -p tsconfig.app.json` — три уже описанные в `REVIEW.md` ошибки `TS2769` в `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/ui-kit/MovementFlowChart.tsx` на строках 39, 84 и 91. Файл относится к атому 5 и не входит в разрешённые файлы атома `WarningNotice`.
- **КРАСНЫЙ вне границы атома 3:** `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting && python3 scripts/ui/ui_guard.py` — храповик сообщил о превышениях в `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/App.tsx`, `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/components/WbProductPickerDialog.tsx`, `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx` и `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/screens/v2/SellerInboundDraftScreen.tsx`. По файлам атома новых нарушений нет; baseline не изменялась.
- **КРАСНЫЙ по ограничению песочницы:** `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting && git add -- frontend/vitest.config.ts night/volna-9-recovery/cards/07-reporting/DEV.md && git diff --cached --check && git commit -m "fix(ui-kit): run WarningNotice unit test"` — Git не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-1-07-reporting1/index.lock`: `Operation not permitted`. Commit SHA отсутствует.

Полные backend `pytest`, `ruff check .` и `mypy .` не запускались согласно атомарной границе.

## Не реализовано

- В самом атоме `WarningNotice` невыполненных пунктов контракта нет.
- Общий `tsc` и `ui_guard.py` не зелёные из-за находок других атомов. Исправления `MovementFlowChart.tsx` и перечисленных экранов не выполнялись, потому что пользователь запретил переходить к следующим атомам и править соседние файлы.
- Результат локально реализован, но не сохранён отдельным Git-коммитом: песочница запрещает запись в общий Git-каталог зарегистрированного worktree.

## Находки

- Находка review №3 для `States.test.tsx` закрыта: после изменения `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/vitest.config.ts` целевой `.test.tsx` обнаруживается и проходит.
- Секреты, ключи, токены, `.env`, кабинеты учётных данных, production `194.87.96.144` и живой кабинет Wildberries не читались и не затрагивались.
