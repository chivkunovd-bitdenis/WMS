# Фича 1

# DEV · 04-warehouse-switch · повторная проверка атома 1

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/night/volna-9-recovery/cards/04-warehouse-switch/DEV.md` — записан результат повторной проверки после `REVIEW.md`.

Backend-код атома не менялся: `REVIEW.md` не содержит находок в
`backend/app/models/warehouse.py`,
`backend/alembic/versions/20260822_0094_warehouse_operational_barcode.py`,
`backend/app/api/warehouses.py` или `backend/tests/test_warehouses.py` и отдельно
подтверждает корректность разделения операционных складов, tenant-проверок resolver-а и
отказа при неоднозначном скане.

## Что реализовано

- `GET /warehouses` — ранее реализованный эндпоинт возвращает только операционные склады tenant; служебные `fbs-wb-*` / `FBS WB *` исключаются сервисом списка.
- `GET /warehouses/resolve` — ранее реализованный resolver возвращает `warehouse` для склада и `location` для ячейки, отклоняет неоднозначное значение как `barcode_ambiguous` и не раскрывает объект другого tenant (`barcode_unknown`).
- `catalog_service.resolve_warehouse_scan` — ранее реализованное разрешение проверяет коды и штрихкоды складов и ячеек в одном tenant без выбора по приоритету.

## Миграции

- Новых миграций нет. Существующая `20260822_0094_warehouse_operational_barcode.py` добавляет `warehouses.is_operational` и `warehouses.barcode`, заполняет уникальные складские штрихкоды и помечает legacy `fbs-wb-*` / `FBS WB *` неоперационными.

## Тесты

- Новых тестов в повторном проходе нет: `backend/tests/test_warehouses.py` уже покрывает список операционных складов, типы `warehouse` / `location`, межсущностную legacy-коллизию и изоляцию чужого tenant.

## Гейты

- `ruff check app/models/warehouse.py app/api/warehouses.py app/services/catalog_service.py alembic/versions/20260822_0094_warehouse_operational_barcode.py tests/test_warehouses.py` (из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend`) — пройдено: `All checks passed!`.
- `mypy app/models/warehouse.py app/api/warehouses.py app/services/catalog_service.py` (из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend`) — целевые модули проверены, но команда завершилась с кодом 1 из-за четырёх существующих ошибок в импортируемых соседних файлах: `wildberries_credentials_service.py:167`, `fbs_stock_sync_service.py:617`, `fbs_warehouse_binding_service.py:23` и `fbs_warehouse_binding_service.py:294`.
- `pytest -q tests/test_warehouses.py` (из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend`) — пройдено: `1 passed in 3.81s`.
- `python3 scripts/ci/back_guard.py` — не применим: повторный проход не добавляет роут; самого файла в рабочей копии также нет.
- `python3 scripts/ci/check_migrations.py` — не применим: повторный проход не добавляет миграцию; самого файла в рабочей копии также нет.

## Не реализовано

- Находки 1–12 из `REVIEW.md` не относятся одновременно к файлам и границам атома 1. Они затрагивают следующие атомы (`preflight`, FBS workspace, общий frontend-контекст, S-01, S-14, S-25, seller draft, движения и blocker registry), поэтому в этом проходе не изменялись.
- В `CONTRACT.md` нет отдельного раздела `API и данные`; точный backend-контракт атома взят из прямо назначенного пользователем пункта 1 `FEATURES.md`. Дополнительное поведение сверх него не добавлялось.

## Блокеры

- Сохранение отчёта отдельным Git-коммитом заблокировано правами среды: команда
  `git add -- night/volna-9-recovery/cards/04-warehouse-switch/DEV.md` завершилась с
  `fatal: Unable to create '/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-1-04-warehouse-switch/index.lock': Operation not permitted`.
  Backend-код не менялся; отчёт записан в рабочую копию, но не сохранён в новом commit SHA.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных и боевой прод не открывались и не изменялись.

# Фича 2

# Backend dev · 04-warehouse-switch · атом 2 · rework

## Что реализовано

- Эндпоинты: новых эндпоинтов нет; существующий FBS-preflight получает расширенный `stock_preflight.warning_lines[].source_warehouses`.
- Сервис `fbs_supply_validator_service._stock_preflight`: распределяет локальный дефицит товара по нескольким операционным складам в порядке доступного покрытия и возвращает точное количество к подбору с каждого склада.
- Сервис `fbs_supply_validator_service.preflight_to_dict`: сериализует агрегированную разбивку источников; legacy-поле `source_warehouse` заполняется только тогда, когда один склад целиком покрывает локальный дефицит.

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/app/services/fbs_supply_validator_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/tests/test_fbs_stock_availability.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/night/volna-9-recovery/cards/04-warehouse-switch/DEV.md`

## Миграции

Нет: атом не меняет схему данных.

## Тесты

- Усилен `test_preflight_aggregates_operational_stock_and_exposes_source_capacity`: потребность 10 единиц при остатках «Юг» 6 и «Север» 4 даёт одну товарную warning-строку и точную разбивку 6+4.
- Тот же тест подтверждает, что 100 единиц служебного склада не входят в общий остаток, рекомендацию или источники подбора.
- Добавлена проверка сериализованного preflight-ответа: при нескольких источниках ложное одиночное указание отсутствует, а `source_warehouses` содержит оба операционных склада и количества.

## Гейты

- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend && ruff check app/services/fbs_supply_validator_service.py tests/test_fbs_stock_availability.py` — пройдено, `All checks passed!`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend && mypy --follow-imports=skip app/services/fbs_supply_validator_service.py` — пройдено, `Success: no issues found in 1 source file`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend && pytest -q tests/test_fbs_stock_availability.py` — пройдено, `9 passed in 36.32s`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch && git diff --check` — пройдено.
- `back_guard.py` не запускался: новый роут не добавлялся.
- `check_migrations.py` не запускался: миграция не добавлялась.

## Не реализовано

- Frontend-потребление нового списка `source_warehouses` не менялось: роль `backend-dev` запрещает правки UI. Backend больше не возвращает ложный одиночный склад при распределённом покрытии; отображение полной разбивки должен выполнить frontend-атом.
- Остальные находки `REVIEW.md` относятся к frontend, сканеру, отчётности и соседним атомам; этот backend-атом их не затрагивает.

## Блокеры

- Код и отчёт локально реализованы, но отдельный Git-коммит создать невозможно из-за прав среды: `git add -- backend/app/services/fbs_supply_validator_service.py backend/tests/test_fbs_stock_availability.py night/volna-9-recovery/cards/04-warehouse-switch/DEV.md` завершился ошибкой `Unable to create '/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-1-04-warehouse-switch/index.lock': Operation not permitted`. Изменения остаются в рабочей копии и пока не имеют восстанавливаемого commit SHA.

## Находки

Нет.

# Фича 3

# DEV · 04-warehouse-switch · атом 3

## Что реализовано

- `GET /operations/fbs-supplies/worklist` — существующий эндпоинт принимает необязательный `warehouse_id` и возвращает только поставки выбранного физического WMS-склада.
- `list_supply_worklist` — проверяет, что склад принадлежит tenant и является операционным, затем фильтрует по неизменяемому `FbsSupply.warehouse_id`; переключение фильтра не переписывает исторический документ.
- Существующие `POST /operations/fbs-supplies/from-orders` и `PATCH /operations/fbs-supplies/{supply_id}/warehouse` подтверждены целевыми тестами: новая поставка принимает рекомендованный или явно выбранный операционный склад, незапущенная меняет его, а после подбора получает `409` с сообщением «Склад закреплён: подбор уже начат».

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/app/api/fbs_supplies.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/app/services/fbs_supply_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/tests/test_fbs_supply_from_orders.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/night/volna-9-recovery/cards/04-warehouse-switch/DEV.md`

## Миграции

Нет.

## Тесты

- Добавлен `test_supply_worklist_filters_by_operational_warehouse`: создаёт две поставки на разных операционных складах, переключает складской фильтр и проверяет, что каждый список содержит только свой документ, а сохранённый `warehouse_id` исторической поставки не меняется.
- Повторно проверены существующие сценарии создания на явно выбранном и рекомендованном складе, смены склада до первого действия, запрета после подбора и группировки списка поставок.

## Гейты

- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend && ruff check app/api/fbs_supplies.py app/services/fbs_supply_service.py tests/test_fbs_supply_from_orders.py` — пройдено: `All checks passed!`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend && mypy app/api/fbs_supplies.py app/services/fbs_supply_service.py tests/test_fbs_supply_from_orders.py` — не пройдено: 4 ранее существовавшие ошибки в импортируемых `wildberries_credentials_service.py`, `fbs_stock_sync_service.py` и `fbs_warehouse_binding_service.py`; в строках текущего diff ошибок нет.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend && pytest -q tests/test_fbs_supply_from_orders.py -k 'warehouse_switch_is_locked_after_pick or creation_uses_selected_operational_warehouse or creation_without_selection_uses_recommended_warehouse or supply_worklist_groups_active_orders_by_supply or supply_worklist_filters_by_operational_warehouse'` — пройдено: `5 passed, 16 deselected in 9.46s`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch && git diff --check` — пройдено, ошибок форматирования diff нет.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch && git add backend/app/api/fbs_supplies.py backend/app/services/fbs_supply_service.py backend/tests/test_fbs_supply_from_orders.py night/volna-9-recovery/cards/04-warehouse-switch/DEV.md && git commit -m 'night(04-warehouse-switch): atom 3/13'` — не выполнено: Git не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-1-04-warehouse-switch/index.lock`, ошибка `Operation not permitted`.
- `python3 scripts/ci/back_guard.py` — не применим: новый маршрут не добавлялся, расширен существующий `GET /operations/fbs-supplies/worklist`, покрытый новым API-тестом.
- `python3 scripts/ci/check_migrations.py` — не применим: миграций в атоме нет.

## Не реализовано

- Находка ревью №1 относится к атомарной фиче 2 и файлу `backend/app/services/fbs_supply_validator_service.py`; в атоме 3 этот сервис не изменялся.
- Находки ревью №2–9 и №12 относятся к frontend или соседним продуктовым атомам; роль `backend-dev` их не меняла.
- Находка ревью №10 относится к внешнему контракту 07-A и модели движений; она не входит в файлы и поведение атома 3.
- Реестр блокировок из находки №11 не менялся: обязательная серверная блокировка `supply_warehouse_locked` уже реализована и проверена здесь, а расширение общего реестра выходит за границы трёх файлов атома.

## Блокеры

- Целевые ruff и pytest пройдены. Единственное ограничение гейтов — ранее существовавшие mypy-ошибки в импортируемых модулях вне текущего diff.
- Результат локально реализован, но не сохранён Git-коммитом: sandbox не разрешает запись в общий служебный каталог `.git`, находящийся вне разрешённого корня worktree. Нужен запуск `git add` и `git commit` процессом с правом записи в основной `.git`.

# Фича 4

# 04-warehouse-switch · screen-dev · атом 4

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/ui-kit/WarehouseContextSwitch.test.tsx` — закреплена граница находки ревью № 5: при пустом подготовленном списке переключатель не рендерится, чтобы экран показал собственный `EmptyState`; при ошибке без вариантов причина остаётся видна. Для `WarningNotice` добавлена проверка, что соседнее главное действие остаётся доступным.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/night/volna-9-recovery/cards/04-warehouse-switch/DEV.md` — отчёт текущего screen-dev прохода.

Файлы реализации `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/ui-kit/WarehouseContextSwitch.tsx`, `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/ui-kit/WarningNotice.tsx` и экспорт из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/ui-kit/index.ts` уже соответствовали контракту, поэтому в этом проходе не изменялись.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend` — красный до проверки проекта: в рабочей копии нет локального `tsc`, а `npx` не смог получить пакет из закрытой сети (`ENOTFOUND registry.npmjs.org`).
- `python3 scripts/ui/ui_guard.py` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch` — красный на ранее изменённых, запрещённых этому атому файлах: `frontend/src/components/WbProductPickerDialog.tsx`, `frontend/src/screens/v2/FfFbsOrdersScreen.tsx`, `frontend/src/screens/v2/FfFbsStockSyncScreen.tsx`, `frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx`, `frontend/src/screens/v2/SellerInboundDraftScreen.tsx`. В файлах атома нового нарушения нет; baseline не обновлялся.
- `npm run test:unit -- --run src/ui-kit/WarehouseContextSwitch.test.tsx` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend` — красный до запуска тестов: `vitest: command not found`, потому что в рабочей копии отсутствует `frontend/node_modules/.bin/vitest`.

## Не реализовано

- Находка ревью № 5 целиком не закрыта: при нуле операционных складов экран S-03 должен показать `EmptyState` и заблокировать складские действия. Это поведение относится к `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/FfFbsOrdersScreen.tsx`, который не входит в файлы атома 4. Сам `WarehouseContextSwitch` по контракту обязан скрываться при 0–1 варианте; это поведение сохранено и теперь явно защищено тестом.
- Остальные находки `REVIEW.md` относятся к backend, контексту приложения или конкретным экранам и не затрагивают разрешённые файлы этого ui-kit атома.

## Находки

Секреты, ключи, токены, `.env`, кабинеты учётных данных и боевой прод `194.87.96.144` не открывались и не изменялись. Новых находок по данным или персональным данным в границах атома нет.

# Фича 5

# DEV · 04-warehouse-switch · атом 5 · rework

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/App.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/contexts/WarehouseContext.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/FfFbsOrdersScreen.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/FfFbsStockSyncScreen.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/utils/fbsWarehouse.test.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/night/volna-9-recovery/cards/04-warehouse-switch/DEV.md`

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` из `frontend/` — **красный до файлов этого атома**: уже закоммиченный `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/FbsSupplyCreateDialog.test.ts` содержит JSX в файле `.ts` (ошибки синтаксиса с строки 55). При первом прогоне до восстановления зависимостей команда ошибочно завершилась без диагностики; после `npm ci --ignore-scripts --prefer-offline` запустился реальный локальный TypeScript и показал дефект соседнего теста.
- `python3 scripts/ui/ui_guard.py` из корня — **красный на ранее накопленном diff ветки**: `WbProductPickerDialog.tsx`, `FfFbsOrdersScreen.tsx`, `FfFbsStockSyncScreen.tsx`, `FfFbsSupplyWorkspace.tsx`, `SellerInboundDraftScreen.tsx`. Baseline не обновлялась. Собственная дельта rework не увеличивает `FfFbsOrdersScreen.tsx` относительно `HEAD` (1663 → 1663 строки), а `FfFbsStockSyncScreen.tsx` уменьшает (1132 → 1120 строк).
- `npm run test:unit` из `frontend/` — **красный до файлов этого атома**: 19 файлов и 148 тестов зелёные, единственный suite `FbsSupplyCreateDialog.test.ts` не преобразуется из-за JSX в `.ts`.
- `npm run test:unit -- --run src/utils/fbsWarehouse.test.ts` — **зелёный**, 1 файл, 6 тестов. Подтверждены: автоподстановка единственного склада, выбор primary вместо `list[0]`, восстановление выбора текущей сессии, отказ от отсутствующего/служебного склада.
- `git diff --check` — **зелёный**.
- Сохранение отдельным Git-коммитом — **заблокировано правами среды**: Git не может создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-1-04-warehouse-switch/index.lock` (`Operation not permitted`). Изменения остались только в рабочем дереве; commit SHA отсутствует.

## Не реализовано

- Три обязательных полных гейта нельзя получить зелёными без правки уже закоммиченных файлов соседних атомов и общей baseline; роль `screen-dev` запрещает такой выход за границы. Baseline флагом `--update` не двигалась.
- Отдельный глобальный контекст склада в seller-портал не добавлялся намеренно: по контракту `SellerApp.tsx` уже передаёт склад только как реквизит заявки, автоматически подставляет единственный склад и очищает загруженный список после logout.
- Живой browser/e2e-сценарий не запускался: в обязательные гейты роли он не входит, а полный unit/tsc слой уже блокируется перечисленным дефектом соседнего теста.
- Публикация в Git не выполнена: общий Git-каталог зарегистрированного worktree недоступен для записи в текущей песочнице. Создание второго репозитория или временного клона не использовалось.

## Находки

- Находка review №4 для слоя атома исправлена: `App`, S-03 и S-04 используют один fulfillment-ключ и одно событие сессионного контекста; локальный ключ S-03 удалён.
- Связанная находка review №5 закрыта в S-03: при нуле операционных складов очередь не показывает данные всех складов и выводит `EmptyState` «Нет рабочего склада» без складских действий.

# Фича 6

# DEV · 04-warehouse-switch · атом 6 · rework

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/App.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/ProductsScreen.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/productsWarehouse.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/ProductsScreen.test.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/tests-e2e/ff-fbs-stock-sync.spec.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/night/volna-9-recovery/cards/04-warehouse-switch/DEV.md`

S-01 теперь получает из общего сессионного контекста только операционные склады и при
смене склада заново запрашивает `/operations/inventory-balances/summary` с его
`warehouse_id`. В таблице меняется только колонка `Остаток`; название, SKU, объём,
селлер и форма товара остаются из исходного каталога. На время смены таблица показывает
`TableSkeletonBody`, а при нуле складов — `EmptyState` с просьбой добавить рабочий склад.

S-04 уже использует общий `useWarehouseContext('fulfillment')`, фильтрует видимые
привязки и доступную массовую синхронизацию по выбранному операционному складу. E2E
дополнен проверкой, что переключение показывает пустую разбивку второго склада и не
вызывает POST публикации остатков. Отдельный сценарий проверяет ноль складов.

`CatalogSection.tsx` не изменялся: по реестру S-01 реализован в `ProductsScreen.tsx`, а
ревью прямо разрешило этот экран и передачу контекста из `App.tsx`. `CatalogSection`
управляет складами и ячейками и не является таблицей товаров S-01.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` из `frontend/` — красный до файлов этого
  атома: `src/screens/v2/FbsSupplyCreateDialog.test.ts:55` содержит JSX в файле `.ts`,
  из-за чего TypeScript выдаёт синтаксические ошибки. Этот соседний тест не входит в
  разрешённый слой атома.
- `python3 scripts/ui/ui_guard.py` из корня — красный на уже накопленных отклонениях:
  `WbProductPickerDialog.tsx`, `FfFbsOrdersScreen.tsx`, `FfFbsStockSyncScreen.tsx`,
  `FfFbsSupplyWorkspace.tsx`, `SellerInboundDraftScreen.tsx`. Новых нарушений в S-01
  и файлах этого прохода guard не показал; baseline не обновлялась.
- `npm run test:unit` из `frontend/` — красный из-за того же соседнего
  `FbsSupplyCreateDialog.test.ts`; остальные 20 файлов и 150 тестов зелёные, включая
  2 новых теста `ProductsScreen.test.ts`.
- `npm run test:unit -- --run src/screens/v2/ProductsScreen.test.ts` — зелёный:
  1 файл, 2 теста.
- `npx eslint src/screens/v2/ProductsScreen.tsx src/screens/v2/productsWarehouse.ts src/screens/v2/ProductsScreen.test.ts tests-e2e/ff-fbs-stock-sync.spec.ts` — зелёный.
- `npx vite build` — зелёный.
- `npx playwright test tests-e2e/ff-fbs-stock-sync.spec.ts --list` — зелёный,
  обнаружены 3 сценария. Живой запуск красный до тестов: sandbox запрещает backend
  привязать `127.0.0.1:18000` (`operation not permitted`).
- `git diff --check` — зелёный.
- Отдельный Git-коммит не создан: sandbox не разрешил создать
  `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-1-04-warehouse-switch/index.lock`
  (`Operation not permitted`). Изменения остаются локальным незакоммиченным diff.

## Не реализовано

- Полный живой Playwright-прогон не выполнен из-за запрета среды на локальный порт;
  сценарии добавлены и успешно разбираются Playwright.
- Три обязательных полных гейта нельзя получить зелёными без правки соседнего атома и
  общей baseline. Эти файлы не менялись, baseline флагом `--update` не двигалась.
- Результат не сохранён в Git из-за запрета записи в служебный каталог worktree;
  восстановимого commit SHA нет.

## Находки

- Секреты, ключи, токены, `.env` и кабинеты учётных данных не читались и не изменялись.

# Фича 7

# DEV · 04-warehouse-switch · атом 7 · rework

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/InboundScreen.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/OutboundScreen.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/tests-e2e/inbound-intake.spec.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/tests-e2e/outbound-submit-storage.spec.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/night/volna-9-recovery/cards/04-warehouse-switch/DEV.md`

На S-22 и S-24 `WarehouseContextSwitch` вынесен из левой колонки в отдельную
строку сразу под заголовком и до всей зависимой области экрана. При открытом
документе строка показывает склад документа и блокирует смену. Сам документ также
показывает имя своего склада текстом; технический ID в интерфейс не выводится.

Действие `К списку` очищает только открытый документ, поэтому переключатель снова
показывает сохранённый склад сессии. Вторые поля `Склад для заявки` и `Склад для
отгрузки` отсутствуют. При одном операционном складе общий переключатель не
рендерится, как требует контракт.

E2E-сценарии дополнены проверкой двух разных складов: оператор выбирает южный склад,
открывает исторический документ северного склада, видит его склад, возвращается к
списку и снова видит южный сессионный контекст. Новый документ сохраняет южный склад,
а список ячеек приёмки не содержит ячейку северного склада.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` из `frontend/` — красный до проверки
  файлов атома: соседний `src/screens/v2/FbsSupplyCreateDialog.test.ts` содержит JSX
  в файле `.ts`, поэтому TypeScript останавливается на синтаксических ошибках строки
  55. Этот файл не входит в разрешённый слой атома 7.
- `python3 scripts/ui/ui_guard.py` из корня — красный только на накопленных
  отклонениях соседних файлов: `WbProductPickerDialog.tsx`, `FfFbsOrdersScreen.tsx`,
  `FfFbsStockSyncScreen.tsx`, `FfFbsSupplyWorkspace.tsx` и
  `SellerInboundDraftScreen.tsx`. Для затронутого `InboundScreen.tsx` guard показывает
  улучшение `экран-монолит 691 → 690`; нового нарушения атом не добавляет. Базовая
  линия не обновлялась.
- `npm run test:unit` из `frontend/` — красный на том же соседнем
  `FbsSupplyCreateDialog.test.ts`; остальные 20 файлов и 150 unit-тестов зелёные.
- `npx eslint src/screens/v2/InboundScreen.tsx src/screens/v2/OutboundScreen.tsx tests-e2e/inbound-intake.spec.ts tests-e2e/outbound-submit-storage.spec.ts` — зелёный.
- `npx playwright test tests-e2e/inbound-intake.spec.ts tests-e2e/outbound-submit-storage.spec.ts --list` — зелёный: обнаружены 2 сценария в 2 файлах.
- Живой запуск тех же двух Playwright-сценариев — заблокирован до выполнения тестов:
  sandbox не разрешил backend привязать `127.0.0.1:18000` (`operation not permitted`).
- `git diff --check` — зелёный.
- `git add` / отдельный commit — красный: sandbox не разрешил создать
  `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-1-04-warehouse-switch/index.lock`
  (`Operation not permitted`). Восстановимого commit SHA для этого rework нет.

## Не реализовано

- Буквально реализованы все пункты контракта атома 7 в разрешённом экранном слое.
- Полный зелёный результат трёх обязательных гейтов недоступен из-за соседнего
  синтаксически неверного теста, накопленной общей baseline UI-guard и запрета среды
  на локальный порт. Эти соседние файлы и baseline не изменялись.
- Живое прохождение двух Playwright-сценариев не выполнено, потому что тестовый сервер
  не смог стартовать в sandbox; сами сценарии успешно разбираются Playwright.
- Результат локально реализован, но не сохранён в Git из-за запрета записи в служебный
  каталог worktree. Изменения остаются незакоммиченным diff.

## Находки

- Находок о данных, персональных данных или утечках в разрешённом слое атома нет.
- Секреты, ключи, токены, `.env` и кабинеты учётных данных не читались и не изменялись.

# Фича 8

# DEV · 04-warehouse-switch · атом 8

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/App.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/TransfersScreen.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/TransfersScreen.test.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/tests-e2e/transfer-and-outbound.spec.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/night/volna-9-recovery/cards/04-warehouse-switch/DEV.md`

`App.tsx` добавлен к двум исходным файлам атома, потому что находка 8 в `REVIEW.md` прямо называет подключение маршрута S-25 в этом файле причиной отсутствия складского контекста и transfer-данных. Другие продуктовые экраны не менялись.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — **красный вне слоя S-25**: компилятор останавливается на `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/FbsSupplyCreateDialog.test.ts:55`, где JSX записан в файле с расширением `.ts`. Отдельная проверка `TransfersScreen.tsx` и его unit-теста с тем же `tsconfig.app.json` и исключённым чужим сломанным тестом — **зелёная**.
- `python3 scripts/ui/ui_guard.py` — **красный вне изменённых экранных файлов**: новые нарушения перечислены в `WbProductPickerDialog.tsx`, `FfFbsOrdersScreen.tsx`, `FfFbsStockSyncScreen.tsx`, `FfFbsSupplyWorkspace.tsx` и `SellerInboundDraftScreen.tsx`. Для `TransfersScreen.tsx` нового нарушения нет; `App.tsx` улучшен с 3492 до 3491 строки. Базовая линия не двигалась.
- `npm run test:unit` — **красный вне слоя S-25**: 21 файл и 152 теста зелёные, единственный failed suite — тот же `FbsSupplyCreateDialog.test.ts`, который esbuild не может разобрать как JSX. Целевая команда `npm run test:unit -- src/screens/v2/TransfersScreen.test.ts` — **зелёная**, 2/2 теста.
- `npx playwright test tests-e2e/transfer-and-outbound.spec.ts --grep "warehouse context filters transfers" --list` — **зелёный**, найден 1 сценарий. Живой запуск той же проверки **заблокирован средой**: Playwright webServer получил `Errno 1 operation not permitted` при bind `127.0.0.1:18000`. Сам сценарий добавлен: Север показывает локальную и межскладскую операции, Юг оставляет соответствующую сторону пары, раскрытие показывает обе ячейки без UUID.
- `git diff --check` — **зелёный**.
- `git add` / отдельный commit — **красный по среде**: Git не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-1-04-warehouse-switch/index.lock` (`Operation not permitted`). Файлы атома не проиндексированы, commit SHA отсутствует; чужой `JOURNAL.md` не захватывался.

## Не реализовано

- Буквальная проверка на живом backend после настоящего cross-warehouse pick не завершена в роли `screen-dev`. Текущий ответ `GET /api/operations/inventory-movements` не содержит нужных экрану полей `transfer_group_id`, `warehouse_id`, `warehouse_name`, `storage_location_code` и `product_name`. S-25 теперь правильно принимает, группирует и фильтрует этот контракт, а E2E закрепляет экранное поведение через API-границу, но реальные пары не появятся до зависимого backend-атома 11, который расширит read-модель журнала.
- Общие красные гейты не исправлены, потому что их причины лежат в соседних файлах и продуктовых атомах, которые роль `screen-dev` и контракт этого атома запрещают менять «заодно».
- Результат локально реализован, но не сохранён в Git: sandbox запрещает запись в служебный каталог worktree, поэтому восстановимого commit SHA нет.

## Находки

- На экранном слое исправлена находка 8: маршрут передаёт операционные склады, выбранный сессионный склад, обработчик смены контекста и движения; при входе S-25 запрашивает свежий журнал. Технические строки с общей transfer-группой собираются в одну строку, а неполная пара не достраивается предположением.
- Секреты, ключи, токены, `.env` и кабинеты учётных данных не читались и не изменялись.

# Фича 9

# DEV · 04-warehouse-switch · переделка атома 9

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/FbsSupplyCreateDialog.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/FbsSupplyCreateDialog.test.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/tests-e2e/ff-fbs-supply.spec.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/night/volna-9-recovery/cards/04-warehouse-switch/DEV.md`

Диалог больше не приписывает весь межскладской дефицит одному складу. Количество рядом с известным складом ограничено фактическим `source_warehouse.available`, а оставшаяся часть честно показана как количество из других складов. Агрегированное предупреждение суммирует одинаковые источники. Кнопка создания при локальной нехватке остаётся доступной после актуального preflight; во время повторной проверки она заблокирована с причиной, старое объяснение остаётся видимым, а запоздавший ответ отменённого запроса не заменяет актуальное состояние.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend` — **красный вне файлов атома**. Единственная оставшаяся причина: `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/ui-kit/WarehouseContextSwitch.test.tsx` импортирует отсутствующий в `package.json` пакет `@testing-library/react` и его DOM-matchers. Ошибок TypeScript в файлах атома 9 нет.
- `python3 scripts/ui/ui_guard.py` из корня — **красный вне файлов атома**: новые нарушения остаются в `WbProductPickerDialog.tsx`, `FfFbsOrdersScreen.tsx`, `FfFbsStockSyncScreen.tsx`, `FfFbsSupplyWorkspace.tsx` и `SellerInboundDraftScreen.tsx`. Изменённый `FbsSupplyCreateDialog.tsx` отмечен guard-ом как улучшение (`своя-кнопка 3 → 2`); базовая линия не менялась.
- `npm run test:unit -- src/screens/v2/FbsSupplyCreateDialog.test.ts` из frontend — **зелёный**, 3/3 теста.
- `npx playwright test tests-e2e/ff-fbs-supply.spec.ts --grep "create supply from selected orders" --list` — **зелёный**, найден один целевой сценарий.
- Живой запуск того же Playwright-сценария — **красный по ограничению среды**: webServer не получил разрешение открыть `127.0.0.1:18000` (`Errno 1 operation not permitted`).
- `git diff --check` — **зелёный**.
- Отдельный commit — **красный по ограничению среды**: Git не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-1-04-warehouse-switch/index.lock` (`Operation not permitted`). Изменения атома не проиндексированы, commit SHA отсутствует; чужой `JOURNAL.md` не захватывался.

## Не реализовано

- Backend preflight по-прежнему возвращает для товарной строки только один известный `source_warehouse`, хотя общий остаток может быть собран с нескольких складов. Фронтенд больше не показывает ложное количество для этого склада и явно обозначает остаток как `другие склады`, но назвать каждый дополнительный склад буквально невозможно без расширения backend-контракта вне разрешённого экранного слоя этого атома.
- Живой E2E-прогон не завершён из-за системного запрета bind порта, описанного в гейтах; тест собран и обнаруживается Playwright.
- Результат локально реализован, но не сохранён в Git: песочница запрещает запись в служебный каталог worktree, поэтому восстановимого commit SHA нет.

## Находки

- Исправлена относящаяся к атому 9 находка №1 из `REVIEW.md`: UI теперь использует фактическое доступное количество источника и не даёт невыполнимое указание забрать весь дефицит с одного склада.
- Секреты, ключи, токены, `.env` и кабинеты учётных данных не читались и не изменялись.

# Фича 10

# DEV · 04-warehouse-switch · атом 10

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/FfFbsSupplyWorkspace.test.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/tests-e2e/ff-fbs-supply.spec.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/night/volna-9-recovery/cards/04-warehouse-switch/DEV.md`

В рабочем месте FBS ключ идемпотентности теперь хранится вместе с `order_id`: сетевой повтор незавершённого подбора использует ту же пару, а следующая физическая единица одинакового SKU выбирает следующий неподобранный заказ и получает новый ключ. Скан ячейки другого склада меняет только место фактического подбора и больше не подменяет показанный склад консолидации документа. Существующая реализация `FfFbsOrdersScreen.tsx` проверена: при нуле операционных складов она уже возвращает `EmptyState` «Нет рабочего склада», а строки без выбранного склада не показывает.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend` — **красный вне файлов атома**. TypeScript не находит уже используемый соседним `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/ui-kit/WarehouseContextSwitch.test.tsx` пакет `@testing-library/react` и его DOM-матчеры. Ошибок в трёх изменённых frontend-файлах команда не показала.
- `python3 scripts/ui/ui_guard.py` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch` — **красный на накопленном diff ветки**: guard считает новыми монолиты `WbProductPickerDialog.tsx`, `FfFbsOrdersScreen.tsx`, `FfFbsStockSyncScreen.tsx`, `FfFbsSupplyWorkspace.tsx` и `SellerInboundDraftScreen.tsx`. Baseline флагом `--update` не менялась.
- `npm run test:unit` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend` — **зелёный**: 22 файла, 156 тестов. Новый `TC-S17-007` подтверждает отдельные ключи для двух одинаковых SKU и повтор последней незавершённой операции тем же ключом.
- `npx playwright test tests-e2e/ff-fbs-supply.spec.ts --grep "scan location then product" --list` — **зелёный**, найден один целевой Chromium-сценарий.
- Живой запуск этого Playwright-сценария — **красный из-за ограничения среды до выполнения теста**: webServer не получил право открыть `127.0.0.1:18000` (`Errno 1 operation not permitted`).
- `git diff --check` — **зелёный**.
- Сохранение отдельным Git-коммитом — **заблокировано правами среды**: `git add` не может создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-1-04-warehouse-switch/index.lock` (`Operation not permitted`). Изменения остаются в рабочем дереве без нового commit SHA.

## Не реализовано

- Общий сессионный контекст из находки ревью № 4 не менялся: его полное исправление требует `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/App.tsx`, `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/contexts/WarehouseContext.tsx` и S-04, которые не входят в разрешённые файлы атома 10. В текущей ветке S-03 уже использует `useWarehouseContext('fulfillment')`, но сквозную согласованность всех экранов этот проход не заявляет.
- Полностью зелёные `tsc` и `ui_guard.py` не получены без выхода за границы атома: причины перечислены в разделе «Гейты».
- Живое прохождение E2E невозможно в этой песочнице из-за запрета bind локального порта; сам сценарий собран Playwright и включает два одинаковых SKU, сетевой повтор, кросс-складскую ячейку и неизменный склад документа.
- Публикация в Git не выполнена: общий Git-каталог зарегистрированного worktree доступен только для чтения. Временный клон и перенос в другую рабочую копию не использовались, поскольку роль требует оставаться в выданной копии.

## Находки

Секреты, ключи, токены, `.env`, кабинеты учётных данных и боевой прод `194.87.96.144` не открывались и не изменялись. Новых находок о данных или персональных данных в разрешённом слое нет.

# Фича 11

# DEV · 04-warehouse-switch · backend-dev · rework атома 11

## Изменённые файлы

- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/tests/test_inventory_movements_report.py
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/docs/blockers/S-03.md
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/night/volna-9-recovery/cards/04-warehouse-switch/DEV.md

## Что реализовано

- Эндпоинты: новых нет; API атома 11 не расширялся.
- Сервисы: существующая атомарная пара `stock_transfer_out` / `stock_transfer_in`, идемпотентный повтор, полный undo и запрет упаковочного обхода не менялись и повторно подтверждены целевыми тестами.
- Writer теста отчётности приведён к обязательному контракту 07-A: каждое прямое создание `InventoryMovement` явно сохраняет фактические `seller_id` и `warehouse_id`, поэтому строгий `NOT NULL` для склада не ослаблен.
- Реестр блокировок S-03 дополнен шестью обязательными полями для `insufficient_sorting_stock` и `foreign_sorting_location`.

## Миграции

- Новых миграций в rework нет. Существующая `20260822_0095_inventory_movement_dimensions` не менялась: `warehouse_id` остаётся обязательным, `seller_id` nullable для обычного FF-товара без селлера.

## Тесты

- Обновлён `test_inventory_movements_summary_groups_and_period_filter`: его прямой writer теперь передаёт селлера и фактический склад для всех движений, включая второй склад.
- Повторно прогнаны `test_fbs_picking.py` и `test_fbs_packaging_integration.py`: связанная пара создаётся один раз, повтор ключа не дублирует её, undo оставляет полную обратную пару, упаковка не списывает из чужой сортировки.

## Гейты

- Воспроизведение находки: `pytest -q tests/test_inventory_movements_report.py::test_inventory_movements_summary_groups_and_period_filter` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend` — до исправления `1 failed`, `NOT NULL constraint failed: inventory_movements.warehouse_id`.
- Целевой ruff: `ruff check tests/test_inventory_movements_report.py` — `All checks passed!`.
- Целевой mypy: `mypy tests/test_inventory_movements_report.py` — `Success: no issues found in 1 source file`.
- Целевой pytest: `pytest -q tests/test_fbs_picking.py tests/test_fbs_packaging_integration.py tests/test_inventory_movements_report.py::test_inventory_movements_summary_groups_and_period_filter` — `25 passed in 22.90s`.
- `python3 scripts/ci/back_guard.py` не запускался: rework не добавляет роут.
- `python3 scripts/ci/check_migrations.py` не запускался: rework не добавляет и не меняет миграцию.
- `git diff --check` — пройден.
- Git-сохранение: `git add backend/tests/test_inventory_movements_report.py docs/blockers/S-03.md night/volna-9-recovery/cards/04-warehouse-switch/DEV.md` — не выполнено, среда запретила создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-1-04-warehouse-switch/index.lock` (`Operation not permitted`).

## Не реализовано

- Находки ревью №1 и №9 относятся к другим backend-атомам (`preflight` и seller inbound), поэтому в атоме 11 не менялись.
- Из находки №11 в реестр внесены две блокировки атома 11; `supply_warehouse_locked` и отсутствие операционного склада принадлежат атомам смены склада и списка, поэтому здесь не переопределялись.
- Frontend-находки №2–8 и №12 не реализовывались: роль ограничена `backend-dev`, а пользователь потребовал только атом 11.
- Строгий контракт `InventoryMovement.warehouse_id` не заменялся nullable/default: это нарушило бы обязательное решение `ARCH-CROSS.md` о неизменяемом фактическом складе движения.

## Находки

- В UI-словаре не найден отдельный человеко-понятный текст для `foreign_sorting_location`; факт записан в B-15 без изменения frontend в backend-атоме.

## Блокеры

- Локально реализовано и проверено, но не сохранено Git-коммитом: sandbox не разрешает запись в общий git-dir зарегистрированного worktree. Риск — изменения можно потерять до запуска с правом записи в `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-1-04-warehouse-switch`.
- Секреты, ключи, токены, `.env`, кабинеты учётных данных и боевой прод не читались и не затрагивались.

# Фича 12

# DEV · 04-warehouse-switch · screen-dev · rework атома 12

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/FfFbsSupplyWorkspace.test.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/tests-e2e/ff-fbs-supply.spec.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/night/volna-9-recovery/cards/04-warehouse-switch/DEV.md`

## Что проверено и закреплено

- Успешный скан склада меняет склад консолидации и оставляет `ScannerLine` в состоянии ожидания склада или ячейки.
- Скан ячейки другого склада выбирает фактическое место подбора, но не переписывает склад консолидации поставки.
- Ошибочный скан сохраняет склад, ячейку и следующий ожидаемый шаг.
- После первого успешного подбора скан другого склада показывает `Склад закреплён: подбор уже начат` и не сбрасывает ячейку.
- Сетевой повтор той же операции сохраняет `order_id` и ключ идемпотентности; вторая физическая единица одинакового SKU выбирает следующий заказ и новый ключ.
- Успешный pick показывает одну строку `Взято: Основной склад / ячейка A-01`, при этом склад консолидации остаётся `Склад Юг`.

Экранная логика для находок ревью №2 и №3 уже присутствовала в текущем `HEAD` после rework предыдущего атома. В этом проходе усилены unit- и E2E-проверки находки №12, чтобы регрессия больше не оставалась зелёной.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend` — красный до проверки изменённых сценариев: существующий `/frontend/src/ui-kit/WarehouseContextSwitch.test.tsx` не находит `@testing-library/react` и DOM-matchers. Изменённые файлы в ошибках не перечислены.
- `python3 scripts/ui/ui_guard.py` из корня — красный на существующих отклонениях базовой линии: `WbProductPickerDialog.tsx`, `FfFbsOrdersScreen.tsx`, `FfFbsStockSyncScreen.tsx`, `FfFbsSupplyWorkspace.tsx` и `SellerInboundDraftScreen.tsx` отмечены как экраны-монолиты. Базовая линия не изменялась.
- `npm run test:unit` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend` — зелёный: 22 файла, 157 тестов.
- `npm run test:unit -- src/screens/v2/FfFbsSupplyWorkspace.test.ts` — зелёный: 1 файл, 5 тестов.
- `npx eslint src/screens/v2/FfFbsSupplyWorkspace.test.ts tests-e2e/ff-fbs-supply.spec.ts` — зелёный.
- `npx playwright test tests-e2e/ff-fbs-supply.spec.ts --grep "scan location then product"` — не запущен до браузерных шагов: sandbox запретил Playwright webServer привязать локальный API к `127.0.0.1:18000` (`operation not permitted`).
- `git diff --check` — зелёный.
- Git-коммит — не создан: среда запретила создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-1-04-warehouse-switch/index.lock` (`Operation not permitted`). Изменения локально реализованы, но не сохранены отдельным коммитом и не опубликованы.

## Не реализовано

- Буквально не выполнен браузерный прогон целевого E2E-сценария: локальный порт запрещён средой выполнения. Сам сценарий прошёл TypeScript/ESLint-разбор в пределах доступных проверок, но это не заменяет запуск Playwright.
- Результат не сохранён в Git из-за запрета записи в общий git-dir worktree; до коммита локальный diff можно потерять.
- Красные `tsc` и `ui_guard.py` не исправлялись, потому что причины находятся в ранее изменённых общем ui-kit и соседних экранах либо требуют выноса более 126 строк из монолита; это выходит за разрешённые файлы и границы атома 12.
- `frontend/src/screens/v2/fbsApi.ts`, `frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx` и `frontend/src/ui-kit/ScannerLine.tsx` не менялись: относящиеся к вердикту исправления в них уже есть, дополнительных расхождений с атомом 12 не найдено.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных и боевой прод не читались и не изменялись.

# Фича 13

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/tests-e2e/seller-cabinet.spec.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/night/volna-9-recovery/cards/04-warehouse-switch/DEV.md`

Экранные файлы
`/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/SellerDocumentsScreen.tsx`,
`/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/SellerInboundDraftScreen.tsx`
и профильный unit-тест были проверены, но в этом повторном проходе не менялись. В них уже есть
требуемые экранные ограничения: S-26 не показывает глобальный складской контекст, список складов
селлера отбрасывает служебные и неоперационные записи, поле склада показывается только для черновика
при двух и более вариантах, а после передачи остаётся текст документа. Ответ PATCH считается успешной
сменой только если вернул выбранный `warehouse_id`; ложный успех не показывается.

E2E-сценарий дополнен отсутствовавшей проверкой из находок 9 и 12: селлер создаёт черновик на «Юге»,
меняет склад на `WH`, проверяет `warehouse_id` в ответе PATCH, перезагружает карточку и убеждается, что
выбор сохранился. После передачи тест повторно открывает документ и проверяет отсутствие селектора и
видимый текст `Склад: WH`. Технические коды складов по-прежнему проверяются как отсутствующие в списке,
а на S-26 по-прежнему проверяется отсутствие глобального `warehouse-context-switch`.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — красный до проверки затронутого сценария: существующий
  `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/ui-kit/WarehouseContextSwitch.test.tsx`
  не может импортировать отсутствующий `@testing-library/react`, после чего TypeScript также не знает
  DOM-матчеры `toBeInTheDocument`, `toBeDisabled`, `toHaveTextContent` и связанные методы. Этот файл и
  зависимости находятся вне разрешённых файлов атома.
- `python3 scripts/ui/ui_guard.py` — красный на ранее накопленных нарушениях baseline:
  `src/components/WbProductPickerDialog.tsx` (0 → 646),
  `src/screens/v2/FfFbsOrdersScreen.tsx` (1587 → 1664),
  `src/screens/v2/FfFbsStockSyncScreen.tsx` (1083 → 1121),
  `src/screens/v2/FfFbsSupplyWorkspace.tsx` (2493 → 2619),
  `src/screens/v2/SellerInboundDraftScreen.tsx` (1111 → 1267). Текущая правка меняет только E2E и не
  добавляет экранной вёрстки; baseline флагом `--update` не двигался.
- `npm run test:unit` — зелёный: 22 test files, 157 tests passed.
- `npm run test:unit -- --run src/screens/v2/sellerInboundDocumentUi.test.ts` — зелёный:
  1 test file, 9 tests passed.
- `npx playwright test tests-e2e/seller-cabinet.spec.ts --grep 'admin creates seller user; seller sees filtered catalog and inbound'`
  — красный до старта браузера: тестовый API не смог привязать `127.0.0.1:18000`, среда вернула
  `[Errno 1] operation not permitted`. Пользовательские шаги в этом запуске не выполнялись.

## Не реализовано

- Смена склада сохранённого черновика не может быть подтверждена буквально на живом API в рамках
  `screen-dev`: серверная схема
  `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/app/api/inbound_intake.py`
  всё ещё не принимает `warehouse_id` в `InboundIntakeRequestPlannedPatch`, а сервисный метод
  `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/app/services/inbound_intake_service.py`
  не меняет склад черновика. Эти backend-файлы не входят в реестр S-26/S-28/S-29 и не относятся к
  слою роли `screen-dev`; они не изменялись. Добавленный E2E теперь фиксирует требуемое поведение и
  станет зелёным только после исправления серверной зависимости.
- Браузерная проверка одного операционного склада не запускалась отдельно. Условие отсутствия поля
  покрыто зелёным unit-тестом `shouldShowSellerWarehouseSelector(1, 'draft') === false`; целевой E2E
  с двумя складами не стартовал из-за запрета локального порта.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных и боевой production не читались и не
  изменялись.
