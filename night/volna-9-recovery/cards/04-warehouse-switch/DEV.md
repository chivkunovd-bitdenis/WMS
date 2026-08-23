# Фича 1

# DEV · 04-warehouse-switch · атом 1

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/App.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/ff/FfPackagingPage.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/ff/FfPackagingPage.test.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/night/volna-9-recovery/cards/04-warehouse-switch/DEV.md`

## Гейты

- ЗЕЛЁНЫЙ — `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend && npx tsc --noEmit -p tsconfig.app.json` (exit 0).
- КРАСНЫЙ ИЗ-ЗА РАНЕЕ ЗАКОММИЧЕННЫХ ФАЙЛОВ ВНЕ ГРАНИЦ АТОМА — `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch && python3 scripts/ui/ui_guard.py` (exit 1). В разрешённых файлах новых нарушений нет: guard сообщает `src/App.tsx: экран-монолит 3492 → 3491` и `src/screens/ff/FfPackagingPage.tsx: экран-монолит 2146 → 2143` как «стало лучше». Красный остаток относится к `src/components/WbProductPickerDialog.tsx`, `src/screens/v2/FfFbsOrdersScreen.tsx`, `src/screens/v2/FfFbsStockSyncScreen.tsx`, `src/screens/v2/FfFbsSupplyWorkspace.tsx` и `src/screens/v2/SellerInboundDraftScreen.tsx`; эти файлы не изменены данным атомом и запрещены роли `screen-dev`.
- ЗЕЛЁНЫЙ — `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend && npm run test:unit -- src/screens/ff/FfPackagingPage.test.ts` (2 теста пройдены, exit 0).
- ЗЕЛЁНЫЙ — `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch && git diff --check` (exit 0).
- КРАСНЫЙ ИЗ-ЗА ОГРАНИЧЕНИЯ SANDBOX — `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch && git add frontend/src/App.tsx frontend/src/screens/ff/FfPackagingPage.tsx frontend/src/screens/ff/FfPackagingPage.test.ts night/volna-9-recovery/cards/04-warehouse-switch/DEV.md && git diff --cached --check && git diff --cached --name-only && git commit -m "fix(packaging): use shared warehouse context"` (exit 128): Git не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-1-04-warehouse-switch/index.lock`, `Operation not permitted`.

## Не реализовано

- Поведение атома реализовано буквально: S-14 получает общий список складов, выбранный `warehouse_id` и обработчик смены из `App`; локального экземпляра `useWarehouseContext` на странице нет; `WarehouseContextSwitch` показан при двух складах; при `null` остаётся существующее пустое состояние и запрос очереди не выполняется.
- Сделать общий `ui_guard.py` зелёным в этой рабочей копии не удалось без правок пяти соседних файлов вне разрешённого списка. Базовая линия не обновлялась, чужие файлы не правились.
- Сохранить результат отдельным Git-коммитом не удалось: sandbox разрешает менять файлы worktree, но запрещает запись в общий Git-каталог зарегистрированного worktree. Второй checkout, клон или временный репозиторий не создавался.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных и боевой production не открывались и не изменялись.

# Фича 2

# DEV · 04-warehouse-switch · атом 2

## Что реализовано

- Эндпоинт `PATCH /operations/inbound-intake-requests/{request_id}`: существующая смена склада теперь блокирует строку заявки и записывает склад только при сохранённом `status='draft'`; проигравшая передаче конкурентная операция получает `409 not_draft`.
- Эндпоинт `POST /operations/inbound-intake-requests/{request_id}/submit`: существующая передача блокирует ту же строку заявки и атомарно переводит только черновик в `submitted`.
- Сервис `inbound_intake_service.get_request`: добавлен режим чтения строки заявки через `SELECT ... FOR UPDATE`.
- Сервис `inbound_intake_service.patch_request_draft`: сохранены `422 invalid_warehouse` для `null`, склада другого tenant и неоперационного склада; добавлена защита от запоздавшего условного `UPDATE`.

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/app/services/inbound_intake_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/tests/test_inbound_intake.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/docs/blockers/S-28.md`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/night/volna-9-recovery/cards/04-warehouse-switch/DEV.md`

## Миграции

Нет.

## Тесты

- Добавлен `test_patch_warehouse_id_foreign_tenant_rejected`: склад другого tenant возвращает `422 invalid_warehouse`.
- Добавлен `test_submit_serializes_concurrent_warehouse_patch`: две независимые PostgreSQL-транзакции удерживают одну строку заявки; передача побеждает, конкурентный PATCH возвращает `409 not_draft`, статус остаётся `submitted`, а `warehouse_id` — исходным.
- Сохранены и повторно пройдены проверки успешной смены склада черновика, `null`, смены после передачи и неоперационного склада.
- В `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/docs/blockers/S-28.md` добавлены две блокировки, у каждой проверены все шесть обязательных полей.

## Гейты

- ЗЕЛЁНЫЙ — `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend && ruff check app/services/inbound_intake_service.py tests/test_inbound_intake.py` — `All checks passed!`, exit 0.
- КРАСНЫЙ В ИМПОРТИРУЕМЫХ МОДУЛЯХ ВНЕ АТОМА — `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend && mypy app/services/inbound_intake_service.py` — exit 1: найдены две ранее существовавшие ошибки в `app/services/wildberries_credentials_service.py:167` и `app/services/fbs_stock_sync_service.py:617`; разрешённые файлы атома они не затрагивают.
- ЗЕЛЁНЫЙ ЦЕЛЕВОЙ — `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend && mypy --follow-imports=skip app/services/inbound_intake_service.py` — `Success: no issues found in 1 source file`, exit 0.
- ЗЕЛЁНЫЙ — `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend && pytest -q tests/test_inbound_intake.py -k 'warehouse_id or submit_serializes_concurrent_warehouse_patch'` — `4 passed, 1 skipped, 18 deselected`, exit 0. PostgreSQL-конкурентный кейс собран и пропущен локально, потому что атомарный pytest настроен на SQLite; маркер `postgresql_concurrency` запускает его в PostgreSQL-контуре.
- ЗЕЛЁНЫЙ — `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch && for field in 'Что блокируется' 'Каким условием' 'Где живёт проверка' 'Что видит оператор' 'Как разблокировать' 'Зачем бизнесово'; do count=$(rg -c "^\\*\\*${field}\\.\\*\\*" docs/blockers/S-28.md); if [ "$count" -ne 2 ]; then echo "$field: $count"; exit 1; fi; echo "$field: $count"; done` — каждое поле найдено дважды, exit 0.
- ЗЕЛЁНЫЙ — `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch && git diff --check` — exit 0.
- КРАСНЫЙ ИЗ-ЗА ОГРАНИЧЕНИЯ SANDBOX — `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch && git add backend/app/services/inbound_intake_service.py backend/tests/test_inbound_intake.py docs/blockers/S-28.md night/volna-9-recovery/cards/04-warehouse-switch/DEV.md && git diff --cached --check && git diff --cached --name-only && git status --short && git commit -m "fix(inbound): serialize warehouse switch and submit"` — exit 128: Git не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-1-04-warehouse-switch/index.lock`, `Operation not permitted`; индекс не изменён и коммит не создан.
- `python3 scripts/ci/back_guard.py` не запускался: атом не добавляет роут.
- `python3 scripts/ci/check_migrations.py` не запускался: атом не добавляет миграцию.
- Полные `pytest`, `ruff check .` и `mypy .` не запускались по запрету атомарного шага.

## Не реализовано

- Пункты атома реализованы буквально; пропущенных пунктов контракта нет.
- Локальный PostgreSQL-прогон конкурентного теста не выполнялся: рабочий тестовый контур этого атома использует SQLite, а роль запрещает менять переменные окружения без отдельного требования. Сам PostgreSQL-кейс добавлен и собирается в целевом pytest.
- Сохранить атом отдельным Git-коммитом не удалось: sandbox разрешает менять файлы зарегистрированного worktree, но запрещает запись в его общий Git-каталог. Второй checkout, клон и временный репозиторий не создавались.

## Блокеры

- Нельзя создать обязательный Git-коммит из этой сессии: общий Git-каталог зарегистрированного worktree недоступен на запись.

## Находки

- Секреты, ключи, токены, файлы `.env`, кабинеты учётных данных, боевой production `194.87.96.144` и живой кабинет Wildberries не открывались и не изменялись.
