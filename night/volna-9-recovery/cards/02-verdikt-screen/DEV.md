# Фича 1

# DEV · 02-verdikt-screen · атом 1

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend/app/services/fbs_marking_service.py` — стартовый маркер WB-проверки теперь записывается через переданный вызывающий `AsyncSession`; отдельная `SessionLocal` и конкурентная транзакция убраны.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend/tests/test_fbs_kiz.py` — добавлен составной регрессионный тест автополла: сессия статусов удерживает заказ через `FOR UPDATE`, WB-маркер не открывает второй сеанс, а свежий отказ WB сохраняется и запрещает сдачу.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/night/volna-9-recovery/cards/02-verdikt-screen/DEV.md` — отчёт этого атома.

## Гейты

- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend && ruff check app/services/fbs_marking_service.py app/services/fbs_autopoll_service.py tests/test_fbs_kiz.py` — пройдено, `All checks passed!`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend && mypy app/services/fbs_marking_service.py app/services/fbs_autopoll_service.py` — не пройдено из-за четырёх существующих ошибок в зависимостях вне атома: `app/services/wildberries_credentials_service.py:167`, `app/services/fbs_stock_sync_service.py:617`, `app/services/fbs_warehouse_binding_service.py:23,291`. В изменённых файлах ошибок не показано.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend && pytest -q tests/test_fbs_kiz.py::test_fbs_autopoll_marking_sync_uses_status_transaction_for_wb_marker` — пройдено, `1 passed in 1.38s`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend && pytest -q tests/test_fbs_kiz.py` — пройдено, `48 passed in 23.07s`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend && git diff --check` — пройдено, вывода нет.
- `back_guard.py` и `check_migrations.py` не запускались: атом не добавляет API-роуты и миграции.

## Не реализовано

- Нет. Выполнен только атом 1 из `FEATURES.md`; атомы 2 и 3 не затрагивались.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных, живой Wildberries и production `194.87.96.144` не читались и не затрагивались.
- Попытка создать отдельный Git-коммит выполнила `git add backend/app/services/fbs_marking_service.py backend/tests/test_fbs_kiz.py night/volna-9-recovery/cards/02-verdikt-screen/DEV.md`, но sandbox запретил создание `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-2-02-verdikt-screen1/index.lock` (`Operation not permitted`). Изменения существуют локально в этой рабочей копии и не закоммичены.

# Фича 2

# DEV · 02-verdikt-screen · атом 2

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/frontend/tests-e2e/ff-fbs-supply.spec.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/night/volna-9-recovery/cards/02-verdikt-screen/DEV.md`

## Гейты

- Зелёный: из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/frontend` выполнено `npx tsc --noEmit -p tsconfig.app.json` (exit 0).
- Красный, не относится к этому атому: из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen` выполнено `python3 scripts/ui/ui_guard.py` (exit 1). Новые нарушения уже находятся вне разрешённого файла: `src/components/WbProductPickerDialog.tsx: экран-монолит 0 → 646` и `src/screens/v2/SellerInboundDraftScreen.tsx: экран-монолит 1111 → 1169`. Базовая линия не изменялась.
- Зелёный: из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/frontend` выполнено `npm run test:unit -- src/screens/v2/FfFbsSupplyWorkspace.test.ts` (1 файл, 3 теста passed).
- Зелёный разбор e2e без серверов: из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/frontend` выполнено `npx playwright test tests-e2e/ff-fbs-supply.spec.ts --grep 'S-03-TC-018' --list` (найден ровно 1 сценарий).
- Блокировано средой до выполнения теста: из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/frontend` выполнено `npx playwright test tests-e2e/ff-fbs-supply.spec.ts --grep 'S-03-TC-018'`; Playwright не смог поднять свой локальный API: `error while attempting to bind on address ('127.0.0.1', 18000): operation not permitted`.

## Не реализовано

Буквальный шаг «вернулся во вкладку и сразу нажал» не может быть доказан в пределах единственного разрешённого тестового файла: текущий экран обновляет открытую поставку раз в 15 секунд только при `document.visibilityState === 'visible'`, но не делает немедленный refresh по `visibilitychange`. Сценарий проверяет существующий безопасный путь: скрытая вкладка не обновляется, после возврата получает сохранённый отказ на ближайшем разрешённом refresh, затем диалог не открывается и `/deliver` не вызывается. Для буквальной немедленной проверки потребовалась бы правка `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx`, которая не входит в файлы атома 2. Полный запуск сценария также не завершён из-за запрета среды на локальный сетевой порт; продуктовый код и другие экранные файлы не менялись.

## Находки

Секреты, ключи, токены, `.env`, кабинеты учётных данных, живой Wildberries и production `194.87.96.144` не читались и не затрагивались.

# Фича 3

# DEV · 02-verdikt-screen · атом 3

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/frontend/tests-e2e/ff-fbs-supply.spec.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/tests/cases/S-03.md`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/night/volna-9-recovery/cards/02-verdikt-screen/DEV.md`

## Гейты

- Зелёный: из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/frontend` выполнено `npx tsc --noEmit -p tsconfig.app.json` (exit 0).
- Красный, не относится к атому: из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen` выполнено `python3 scripts/ui/ui_guard.py` (exit 1). Новые нарушения в неразрешённых для атома файлах: `src/components/WbProductPickerDialog.tsx: экран-монолит 0 → 646` и `src/screens/v2/SellerInboundDraftScreen.tsx: экран-монолит 1111 → 1169`. Базовая линия не изменялась.
- Зелёный: из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/frontend` выполнено `npm run test:unit -- src/screens/v2/FfFbsSupplyWorkspace.test.ts` (1 файл, 3 теста passed).
- Зелёный: из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/frontend` выполнено `npx playwright test tests-e2e/ff-fbs-supply.spec.ts --grep 'S-03-TC-019' --list`; найден ровно один сценарий с `S-03-TC-019`.
- Блокировано средой: из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/frontend` выполнено `npx playwright test tests-e2e/ff-fbs-supply.spec.ts --grep 'S-03-TC-019'`; Playwright не смог поднять локальный API, потому что привязка `127.0.0.1:18000` запрещена (`operation not permitted`).
- Зелёный: из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen` выполнено `git diff --check` (exit 0).
- Сохранение в Git заблокировано средой: `git add frontend/tests-e2e/ff-fbs-supply.spec.ts tests/cases/S-03.md night/volna-9-recovery/cards/02-verdikt-screen/DEV.md` не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-2-02-verdikt-screen1/index.lock` (`Operation not permitted`). Поэтому отдельный commit SHA отсутствует.

## Не реализовано

Нет. Сценарий гонки refresh получил отдельный канонический идентификатор `S-03-TC-019`; комментарий и название Playwright-теста ссылаются на него, а `S-03-TC-007` остаётся сценарием агрегации нескольких метаданных одного заказа. Фактический запуск целевого Playwright-теста не завершён только из-за запрета среды на локальный порт.

## Находки

Секреты, ключи, токены, `.env`, кабинеты учётных данных, живой Wildberries и production `194.87.96.144` не читались и не затрагивались.
