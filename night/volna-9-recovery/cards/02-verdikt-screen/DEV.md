# Фича 1

# DEV · 02-verdikt-screen · атом 1

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend/app/services/fbs_marking_service.py` — маркер старта WB-проверки фиксируется до внешнего запроса; отключена синхронизация SQLAlchemy identity map для сравнения UTC-aware времени с SQLite-значением.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend/tests/test_fbs_marking.py` — S-03-TC-016 ограничивает ожидание старта второго WB-запроса двумя секундами, поэтому возврат SQLite-блокировки выявляется без зависания.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/night/volna-9-recovery/cards/02-verdikt-screen/DEV.md` — отчёт этого атома.

## Гейты

- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend && ruff check app/services/fbs_marking_service.py tests/test_fbs_marking.py` — `All checks passed!`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend && mypy app/services/fbs_marking_service.py` — не пройден из-за четырёх существующих ошибок в импортируемых `wildberries_credentials_service.py`, `fbs_stock_sync_service.py` и `fbs_warehouse_binding_service.py`; изменённые строки не названы.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend && mypy --follow-imports=skip --disable-error-code=no-any-return app/services/fbs_marking_service.py` — `Success: no issues found in 1 source file`; подавлен только существующий `no-any-return` в незатронутых строках модуля.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend && pytest -q tests/test_fbs_marking.py -k 'does_not_apply_stale_response'` — `2 passed, 31 deselected`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend && pytest -q tests/test_fbs_kiz.py -k 'fbs_autopoll_marking_sync_uses_status_transaction_for_wb_marker'` — `1 passed, 47 deselected`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend && pytest -q tests/test_fbs_marking.py` — `33 passed`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen && git diff --check` — пройден.
- `back_guard.py` и `check_migrations.py` не запускались: этот атом не добавляет маршрут или миграцию.

## Не реализовано

- Нет. Выполнен только атом 1 из `FEATURES.md`; атомы 2 и 3 не затрагивались.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных, живой Wildberries и production `194.87.96.144` не читались и не затрагивались.
- Отдельный Git-коммит не создан: sandbox запретил создание `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-2-02-verdikt-screen1/index.lock` (`Operation not permitted`). Изменения существуют локально в этой рабочей копии и не закоммичены.

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
