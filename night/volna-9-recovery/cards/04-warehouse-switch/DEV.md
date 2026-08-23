# Фича 1

# DEV · 04-warehouse-switch · атом 1 · rework

## Что реализовано

- Эндпоинт `PATCH /operations/inbound-intake-requests/{id}` принимает явно переданный `warehouse_id`, передаёт значение и `warehouse_id_set` в сервис и возвращает документ с обновлённым складом.
- Сервис `inbound_intake_service.patch_request_draft` меняет склад только у документа в статусе `draft`; это отдельная охрана для `warehouse_id`, поэтому существующее право селлера менять прочие плановые поля после передачи не расширяет право менять закреплённый склад.
- Новый склад загружается в границах `tenant_id` и принимается только при `Warehouse.is_operational == True`; отсутствующий, чужой, неоперационный или явно `null` склад возвращает известный код `invalid_warehouse`.
- После передачи заявки попытка селлера сменить склад возвращает `409 not_draft`.

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/app/services/inbound_intake_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/tests/test_inbound_intake.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/night/volna-9-recovery/cards/04-warehouse-switch/DEV.md`

API-схема и проброс `warehouse_id` в `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/app/api/inbound_intake.py` уже находились в HEAD после предыдущего атомарного коммита; в этом rework файл не менялся.

## Миграции

Нет. Атом расширяет поведение существующего PATCH и не меняет структуру базы данных.

## Тесты

- `test_patch_warehouse_id_saves_on_draft` проверяет `200`, сохранение второго операционного склада и `422 invalid_warehouse` для явно переданного `null`.
- `test_patch_warehouse_id_rejected_after_submission` теперь проходит через учётную запись селлера и проверяет `409 not_draft` после передачи заявки.
- `test_patch_warehouse_id_non_operational_rejected` проверяет `422 invalid_warehouse` для неоперационного склада.
- Фильтр `-k "warehouse"` также выполнил два относящихся к складу регрессионных теста этого файла.

## Гейты

- Рабочий каталог `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch`; команда `pytest -q backend/tests/test_inbound_intake.py -k "warehouse"` — успешно: `5 passed, 16 deselected in 7.46s`.
- Рабочий каталог `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend`; команда `ruff check app/api/inbound_intake.py app/services/inbound_intake_service.py tests/test_inbound_intake.py` — успешно: `All checks passed!`.
- Рабочий каталог `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend`; команда `mypy app/api/inbound_intake.py app/services/inbound_intake_service.py` — завершилась с кодом 1 из-за двух существующих ошибок в импортированных соседних модулях: `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/app/services/wildberries_credentials_service.py:167` и `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/app/services/fbs_stock_sync_service.py:617`.
- Рабочий каталог `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend`; команда `mypy --follow-imports=silent app/api/inbound_intake.py app/services/inbound_intake_service.py` — успешно: `Success: no issues found in 2 source files`.
- Рабочий каталог `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch`; команда `git diff --check -- backend/app/services/inbound_intake_service.py backend/tests/test_inbound_intake.py night/volna-9-recovery/cards/04-warehouse-switch/DEV.md` — успешно, ошибок пробелов нет.
- Рабочий каталог `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch`; команда `git add backend/app/services/inbound_intake_service.py backend/tests/test_inbound_intake.py night/volna-9-recovery/cards/04-warehouse-switch/DEV.md` — не выполнена средой: Git не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-1-04-warehouse-switch/index.lock` (`Operation not permitted`).
- `back_guard.py` не запускался: новый роут не добавлялся, изменено поведение уже существующего PATCH.
- `check_migrations.py` не запускался: миграций нет.
- Полные `pytest`, `ruff check .` и `mypy .` не запускались согласно ограничению атомарной проверки.

## Не реализовано

- Frontend-находки 1 и 3 из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/night/volna-9-recovery/cards/04-warehouse-switch/REVIEW.md` не реализованы: они относятся к ролям `screen-dev` и отдельным атомам 3–4 в `FEATURES.md`.
- Проверка наличия тарифа и ячеек у нового склада не добавлялась: `FEATURES.md` явно оставляет её за границами атома.

## Находки

- Предыдущая проверка блокировки после передачи использовала администратора и не ловила разрешение `_request_plan_editable` для селлера в статусе `submitted`; тест усилен seller-сценарием, а сервис получил отдельную draft-охрану именно для `warehouse_id`.
- Секреты, ключи, токены, `.env`, кабинеты учётных данных и production не открывались и не изменялись.

## Блокеры

- Локальная реализация и артефакт не сохранены новым коммитом: sandbox разрешает запись в worktree, но запрещает запись в общий Git-каталог `/Users/deniscivkunov/Projects/WMS/.git`, где находится индекс зарегистрированной рабочей копии. Создание второго репозитория или временного клона не выполнялось, потому что это прямо запрещено правилами проекта.

# Фича 3

# DEV · 04-warehouse-switch · атом 3 (S-14)

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/ff/FfPackagingPage.test.ts` — добавлен атомарный регрессионный unit-тест `S-14-TC-001`: он фиксирует передачу `warehouse_id`, перезагрузку при смене `selectedWarehouseId`, ранний выход без запроса и показ `WarehouseNoContextState` при нулевом складском контексте.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/night/volna-9-recovery/cards/04-warehouse-switch/DEV.md` — записан обязательный отчёт роли `screen-dev`.

Экранная реализация в `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/ff/FfPackagingPage.tsx` уже находилась в текущей ветке: основная часть сохранена коммитом `44efc687e8cf22af71ea09db6d7c5485bcfe86b7`, а буквальная зависимость `selectedWarehouseId` в `useEffect` — коммитом `4a15595402a90d2b1518d057895e4632d2d1f2d7`. Повторно переписывать корректный экран не потребовалось.

## Гейты

- `npm run test:unit -- src/screens/ff/FfPackagingPage.test.ts` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend` — зелёный, код 0: 1 файл, 2 теста прошли.
- `npx tsc --noEmit -p tsconfig.app.json` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend` — зелёный, код 0, ошибок нет.
- `python3 scripts/ui/ui_guard.py` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch` — красный, код 1. Разрешённый экран `FfPackagingPage.tsx` и его тест среди новых нарушений не названы. Скрипт сообщает о ранее существующих монолитах вне атома: `WbProductPickerDialog.tsx` (0 → 646), `FfFbsOrdersScreen.tsx` (1587 → 1690), `FfFbsStockSyncScreen.tsx` (1083 → 1121), `FfFbsSupplyWorkspace.tsx` (2493 → 2605) и `SellerInboundDraftScreen.tsx` (1111 → 1267). Базовая линия не изменялась.
- `npm run build` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend` — зелёный, код 0; Vite собрал production bundle. Предупреждение о крупных чанках не является ошибкой.
- `git diff --check` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch` — зелёный, ошибок пробелов нет.
- `git add frontend/src/screens/ff/FfPackagingPage.test.ts night/volna-9-recovery/cards/04-warehouse-switch/DEV.md` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch` — красный: Git не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-1-04-warehouse-switch/index.lock` (`Operation not permitted`). Поэтому новый commit и push этого прохода технически невозможны в текущем sandbox.
- Полные backend `pytest`, `ruff check .` и `mypy .` не запускались согласно прямому запрету атомарной проверки.

## Не реализовано

- Все пункты атома в разрешённом экранном файле реализованы буквально: используется `useWarehouseContext('fulfillment')`; без `selectedWarehouseId` список очищается и запрос не выполняется; параметр `warehouse_id` передаётся в `/operations/packaging-tasks`; `selectedWarehouseId` входит в зависимости `useCallback` и `useEffect`; при нулевом контексте показан `WarehouseNoContextState`. Новых колонок, чипов и действий не добавлено.
- Ручной браузерный сценарий «Север → Юг → ноль складов» не выполнялся: роль `screen-dev` реализует экран и технические проверки, а живая продуктовая браузерная приёмка должна выполняться отдельной ролью после разработки.
- Общий `ui_guard.py` не зелёный из-за пяти чужих файлов вне разрешённой области этого атома; исправлять их или обновлять baseline роль `screen-dev` не имеет права.
- Новый unit-тест и текущая версия `DEV.md` локально реализованы, но не сохранены новым коммитом и не опубликованы из-за запрета записи в общий Git-каталог worktree. Основная экранная реализация S-14 остаётся сохранённой в коммитах `44efc687e8cf22af71ea09db6d7c5485bcfe86b7` и `4a15595402a90d2b1518d057895e4632d2d1f2d7`.

## Находки

- Из трёх пунктов `REVIEW.md` к этому атому и разрешённому файлу относится только находка 1 по S-14. Находки 2 (S-28 backend) и 3 (гонка S-03) не затрагивались.
- Секреты, ключи, токены, `.env`, кабинеты учётных данных и боевой production не открывались и не изменялись.

# Фича 4

# DEV · 04-warehouse-switch · атом 4 · переделка по REVIEW.md

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/FfFbsOrdersScreen.tsx` — `load()` переведён на единый механизм замены незавершённого запроса; при исчезновении складского контекста активный запрос также прерывается.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/fbsApi.ts` — добавлен тестируемый `runLatestFbsOrdersLoad`: новый запуск прерывает прежний `AbortController`, молча принимает `AbortError` и завершает индикатор только для актуального запроса. Ранее добавленные `signal` в `fetchFbsWorklist` и `fetchFbsSupplyWorklist` сохранены.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/fbsApi.test.ts` — добавлен регрессионный `S-03-TC-001`: медленная загрузка «Севера» прерывается сменой на «Юг», второй запрос стартует немедленно, ошибки в state нет, итоговый state содержит только данные «Юга».
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/night/volna-9-recovery/cards/04-warehouse-switch/DEV.md` — отчёт этого атомарного прохода.

До начала прохода уже был изменён `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/night/volna-9-recovery/JOURNAL.md`; это чужое изменение не редактировалось и в атом не входит.

## Гейты

- Рабочий каталог `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend`; команда `npm run test:unit -- src/screens/v2/fbsApi.test.ts` — зелёная, код 0: `1 passed` файл, `10 passed` тестов.
- Рабочий каталог `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend`; команда `npx tsc --noEmit -p tsconfig.app.json` — зелёная, код 0, ошибок нет.
- Рабочий каталог `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch`; команда `python3 scripts/ui/ui_guard.py` — красная, код 1. Скрипт повторно сообщает о накопленных до этого прохода монолитах: `WbProductPickerDialog.tsx` (`0 → 646`), `FfFbsOrdersScreen.tsx` (`1587 → 1676`), `FfFbsStockSyncScreen.tsx` (`1083 → 1121`), `FfFbsSupplyWorkspace.tsx` (`2493 → 2605`) и `SellerInboundDraftScreen.tsx` (`1111 → 1267`). Baseline не изменялся. Текущий атом не ухудшил целевой экран: в `HEAD` было 1689 строк, после переделки — 1675 строк.
- Рабочий каталог `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch`; команда `git diff --check` — зелёная, ошибок пробелов нет.
- Рабочий каталог `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch`; команда `git add frontend/src/screens/v2/FfFbsOrdersScreen.tsx frontend/src/screens/v2/fbsApi.ts frontend/src/screens/v2/fbsApi.test.ts night/volna-9-recovery/cards/04-warehouse-switch/DEV.md && git diff --cached --check && git commit -m "fix(fbs): cancel stale warehouse worklist loads"` — красная до стадии индексации: Git не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-1-04-warehouse-switch/index.lock` (`Operation not permitted`). Чужой `JOURNAL.md` в команду не включался.
- Полные frontend/backend regression suites, полный `pytest`, `ruff check .` и `mypy .` не запускались: для этого атома прямо разрешены только его тестовый файл и относящиеся к вердикту проверки.

## Не реализовано

- Из требований атома 4 ничего не пропущено: прежний запрос прерывается, новый начинается без ожидания, все вызовы worklist внутри `load()` получают `signal`, `AbortError` не записывается в state, поллинг сохраняет семантику «последний тик побеждает», а гонка «Север → Юг» закреплена unit-тестом с проверкой итогового state.
- Находки 1 (S-14 frontend) и 2 (S-28 backend) из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/night/volna-9-recovery/cards/04-warehouse-switch/REVIEW.md` не трогались: пользователь назначил только атом 4 и запретил переходить к соседним задачам.
- `ui_guard.py` не удалось сделать зелёным буквально: он сравнивает всю ветку с baseline и видит пять накопленных монолитов, существовавших до текущего прохода. Разбиение этих экранов и обновление baseline запрещены границами роли и атома; новых отклонений в текущем diff нет.
- Живой браузерный проход не выполнялся: роль `screen-dev` ограничена реализацией и атомарными техническими проверками; продуктовая браузерная приёмка выполняется отдельной ролью после разработки.
- Отдельный commit и push не созданы: sandbox разрешает запись в worktree, но запрещает создание Git lock-файла в общем каталоге зарегистрированного worktree. Создавать второй checkout или временный клон запрещено правилами проекта, поэтому результат остаётся локально реализованным, но не сохранённым в новом Git-коммите.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных и боевой production не открывались и не изменялись.
