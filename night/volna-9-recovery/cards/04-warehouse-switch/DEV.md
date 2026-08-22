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

- Эндпоинты: новых эндпоинтов нет; существующий FBS-preflight уже возвращает агрегированные `warning_lines`/`blocking_lines` и точную разбивку `source_warehouses[]` только по операционным складам tenant.
- Сервис `fbs_warehouse_binding_service`: сохранён запрет активной WB→WMS-привязки к служебному складу; устранены ошибки строгой типизации исключения, legacy-проверки служебного склада и ответа сводки пула без изменения поведения.
- Сервисы `fbs_stock_availability_service` и `fbs_supply_validator_service`: проверены без дополнительных изменений — служебный остаток исключён, рекомендация выбирает максимальное покрытие и при равенстве оставляет текущий склад, локальная нехватка предупреждает, а общая нехватка блокирует.

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/app/services/fbs_warehouse_binding_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/tests/test_fbs_stock_availability.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/night/volna-9-recovery/cards/04-warehouse-switch/DEV.md`

## Миграции

Нет: атом не меняет схему данных.

## Тесты

- Усилен `test_preflight_aggregates_operational_stock_and_exposes_source_capacity`: потребность 10 единиц при остатках «Юг» 6 и «Север» 4 даёт одну агрегированную предупреждающую строку, не блокирует создание и сериализует точную разбивку 6+4.
- В том же сценарии 100 единиц служебного склада не входят в общий остаток, рекомендацию или источники подбора.
- Добавлена вторая фаза сценария: при потребности 20 и общем операционном остатке 16 preflight блокирует создание с дефицитом 4; при равном покрытии 6 единиц на текущем складе и «Юге» рекомендацией остаётся текущий склад.

## Гейты

- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend && ruff check app/services/fbs_warehouse_binding_service.py app/services/fbs_stock_availability_service.py app/services/fbs_supply_validator_service.py tests/test_fbs_stock_availability.py` — пройдено, `All checks passed!`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend && mypy --follow-imports=skip app/services/fbs_warehouse_binding_service.py app/services/fbs_stock_availability_service.py app/services/fbs_supply_validator_service.py` — пройдено, `Success: no issues found in 3 source files`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend && pytest -q tests/test_fbs_stock_availability.py` — пройдено, `9 passed in 7.56s`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch && git diff --check -- backend/app/services/fbs_warehouse_binding_service.py backend/tests/test_fbs_stock_availability.py` — пройдено без замечаний.
- `back_guard.py` не запускался: новый роут не добавлялся.
- `check_migrations.py` не запускался: миграция не добавлялась.

## Не реализовано

- Находка ревью №1 требует научить frontend читать уже возвращаемый backend-массив `source_warehouses[]`. Файлы `frontend/src/screens/v2/fbsApi.ts` и `frontend/src/screens/v2/FbsSupplyCreateDialog.tsx` не изменялись: роль `backend-dev` запрещает UI-правки. Backend не подменён ложным одиночным `source_warehouse`, потому что при покрытии 6+4 один склад физически не закрывает дефицит.
- Находки ревью №2–6 относятся к другим frontend/backend-атомам и к файлам вне назначенного слоя атома 2; они не затрагивались.
- В `CONTRACT.md` нет отдельного раздела `API и данные`; точный backend-контракт взят из прямо назначенного пользователем атома 2 в `FEATURES.md` и уже принятых решений `RESHENIYA.md`/`ARCH-CROSS.md`. Поведение сверх него не добавлялось.

## Блокеры

- Код и отчёт локально реализованы, но отдельный Git-коммит создать невозможно из-за прав среды: команда `git add -- backend/app/services/fbs_warehouse_binding_service.py backend/tests/test_fbs_stock_availability.py night/volna-9-recovery/cards/04-warehouse-switch/DEV.md` завершилась ошибкой `Unable to create '/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-1-04-warehouse-switch/index.lock': Operation not permitted`. Изменения находятся в постоянной рабочей копии, но не имеют нового восстанавливаемого commit SHA.

## Находки

Нет находок по данным, утечкам, секретам или персональным данным; такие источники не открывались.

# Фича 3

# Backend dev · 04-warehouse-switch · атом 3 · rework

## Что реализовано

- `GET /operations/fbs-supplies/worklist` — подтверждена фильтрация по операционному `warehouse_id` текущего tenant без изменения склада исторической поставки.
- `POST /operations/fbs-supplies/from-orders` — подтверждено создание поставки на рекомендованном или явно выбранном операционном складе.
- `PATCH /operations/fbs-supplies/{supply_id}/warehouse` — подтверждена смена склада до начала работы и блокировка после подбора с сообщением «Склад закреплён: подбор уже начат».
- `_raise_from_packaging_integration` — `insufficient_sorting_stock` и `foreign_sorting_location` теперь возвращаются как штатный конфликт `409`, сохраняют конкретное сообщение сервиса и имеют русское резервное объяснение вместо HTTP 500 с техническим кодом.
- Реестр блокировок S-03 — исправлены B-14/B-15 и добавлены отсутствовавшие B-16 `supply_warehouse_locked` и B-17 выбора только операционного склада tenant.

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/app/api/fbs_supplies.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/tests/test_fbs_supply_from_orders.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/docs/blockers/S-03.md`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/night/volna-9-recovery/cards/04-warehouse-switch/DEV.md`

## Миграции

Нет.

## Тесты

- Добавлен параметризованный `test_packaging_warehouse_blocks_return_operator_message`: проверяет для `insufficient_sorting_stock` и `foreign_sorting_location` статус `409`, стабильный error envelope, сохранение конкретного сообщения сервиса и человеко-понятный резервный текст.
- Повторно проверены создание поставки на рекомендованном и вручную выбранном операционном складе, смена склада до первого действия, запрет после подбора, группировка worklist и фильтрация существующих поставок по собственному `warehouse_id`.

## Гейты

- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend && ruff check app/api/fbs_supplies.py app/services/fbs_supply_service.py tests/test_fbs_supply_from_orders.py` — пройдено: `All checks passed!`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend && mypy app/api/fbs_supplies.py app/services/fbs_supply_service.py tests/test_fbs_supply_from_orders.py` — целевые файлы текущего атома чисты, команда завершилась с кодом 1 из-за двух ошибок в импортируемых соседних модулях вне атома: `app/services/wildberries_credentials_service.py:167` и `app/services/fbs_stock_sync_service.py:617`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend && pytest -q tests/test_fbs_supply_from_orders.py -k 'packaging_warehouse_blocks_return_operator_message or warehouse_switch_is_locked_after_pick or creation_uses_selected_operational_warehouse or creation_without_selection_uses_recommended_warehouse or supply_worklist_groups_active_orders_by_supply or supply_worklist_filters_by_operational_warehouse'` — пройдено: `7 passed, 16 deselected in 5.01s`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch && git diff --check` — пройдено без замечаний.
- Диагностическая попытка `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend && mypy --follow-imports=skip app/api/fbs_supplies.py app/services/fbs_supply_service.py` не засчитана как гейт: пропуск импортов превратил типы FastAPI/Pydantic в `Any` и дал 144 ложных ошибки; после неё выполнена штатная целевая команда выше.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch && git add -- backend/app/api/fbs_supplies.py backend/tests/test_fbs_supply_from_orders.py docs/blockers/S-03.md night/volna-9-recovery/cards/04-warehouse-switch/DEV.md && git diff --cached --check && git diff --cached --stat && git commit -m 'fix(fbs): map warehouse packaging blocks'` — не выполнено: Git не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-1-04-warehouse-switch/index.lock`, ошибка `Operation not permitted`.
- `python3 scripts/ci/back_guard.py` — не запускался: новых маршрутов атом не добавляет.
- `python3 scripts/ci/check_migrations.py` — не запускался: миграций нет.

## Не реализовано

- Frontend-находки REVIEW №1, №2, №3 и №6 не менялись: роль `backend-dev` и границы атома запрещают UI-правки.
- Находка REVIEW №4 относится к соседнему backend-контракту черновика приёмки (`inbound_intake.py`), а не к FBS-поставке атома 3.
- `backend/app/services/fbs_supply_service.py` не потребовал нового diff: создание, смена/закрепление склада и фильтрация worklist уже реализованы буквально и подтверждены назначенными тестами.

## Блокеры

- Реализация и артефакт находятся в постоянном зарегистрированном worktree, но не сохранены отдельным Git-коммитом: sandbox разрешает менять рабочие файлы, однако запрещает запись в общий служебный каталог `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-1-04-warehouse-switch`. Восстанавливаемого нового commit SHA нет.
- Целевые ruff и pytest зелёные; mypy остановлен только двумя ранее существовавшими ошибками импортируемых соседних модулей вне файлов атома.

## Находки

Нет.

# Фича 4

# DEV · 04-warehouse-switch · screen-dev · rework атома 4

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/ui-kit/WarehouseContextSwitch.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/ui-kit/WarehouseContextSwitch.test.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/ui-kit/WarehouseContextSwitch.runner.test.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/night/volna-9-recovery/cards/04-warehouse-switch/DEV.md`

Находка №6 из `REVIEW.md` исправлена без добавления отсутствующей зависимости
`@testing-library/react`: контрактный TSX-suite теперь проверяет React-дерево и обработчики
компонента штатными React/Vitest-средствами. Поскольку текущий `vitest.config.ts` обнаруживает только
`src/**/*.test.ts`, добавлен минимальный `WarehouseContextSwitch.runner.test.ts`, который загружает
контрактный `WarehouseContextSwitch.test.tsx`. Теперь suite действительно запускается и проверяет
скрытие при 0–1 складе, раскрытие выбора, показ только имён, вызов `onChange`, закрытие после выбора,
загрузочное, недоступное и ошибочное состояния, а также неблокирующий `WarningNotice`.

В `WarehouseContextSwitch` меню получило производный от уже переданного `testId` стабильный
`data-testid`; видимое поведение и публичный интерфейс компонента не изменились.

## Гейты

- `npm run test:unit -- --run src/ui-kit/WarehouseContextSwitch.test.tsx` из
  `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend`
  — **красный, диагностический запуск**: Vitest сообщил `No test files found`, подтвердив замечание
  ревью о маске `src/**/*.test.ts`.
- `npx tsc --noEmit -p tsconfig.app.json` из
  `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend`
  — **зелёный**.
- `npm run test:unit -- --run src/ui-kit/WarehouseContextSwitch.runner.test.ts` из
  `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend`
  — **зелёный**: 1 файл, 7 тестов.
- `python3 scripts/ui/ui_guard.py` из
  `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch`
  — **красный на накопленных изменениях соседних атомов**: guard отмечает монолиты
  `frontend/src/components/WbProductPickerDialog.tsx`,
  `frontend/src/screens/v2/FfFbsOrdersScreen.tsx`,
  `frontend/src/screens/v2/FfFbsStockSyncScreen.tsx`,
  `frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx` и
  `frontend/src/screens/v2/SellerInboundDraftScreen.tsx`. Файлы атома 4 новых нарушений не добавили;
  baseline флагом `--update` не менялась.
- `npm run build` из
  `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend`
  — **зелёный**: `tsc -b` и production-сборка Vite завершились успешно. Осталось штатное
  предупреждение Vite о размере нескольких существующих chunks.
- `git diff --check` из
  `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch`
  — **зелёный**.

Полный backend pytest, `ruff check .`, `mypy .` и полный frontend unit-набор не запускались: для этого
атомарного шага пользователь прямо разрешил только тесты данного атома и относящиеся к нему регрессии.

## Не реализовано

- Полностью зелёный `ui_guard.py` нельзя получить в границах атома 4: все пять оставшихся нарушений
  относятся к соседним экранам, которые роль `screen-dev` в этом проходе менять запрещает.
- Отдельных нереализованных пунктов контракта компонентов нет. Находка №6 из повторного ревью,
  относящаяся к разрешённым файлам и слою атома 4, закрыта и проверена целевым suite и сборкой.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных, живой кабинет Wildberries и боевой прод
  `194.87.96.144` не читались и не изменялись.

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

# Screen dev · 04-warehouse-switch · атом 9 · rework

Исправлена относящаяся к preflight находка №1 из `REVIEW.md`: диалог теперь читает точную серверную разбивку `source_warehouses[]` и показывает оператору каждый склад с исполнимым количеством. Для ответа «Юг — 6, Север — 4» больше не выводится безымянный остаток «другие склады — 4».

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/fbsApi.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/FbsSupplyCreateDialog.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/FbsSupplyCreateDialog.test.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/tests-e2e/ff-fbs-supply.spec.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/night/volna-9-recovery/cards/04-warehouse-switch/DEV.md`

## Гейты

- Зелёный: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend && npx tsc --noEmit -p tsconfig.app.json`.
- Зелёный: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend && npm run test:unit -- src/screens/v2/FbsSupplyCreateDialog.test.ts` — 1 файл, 3 теста прошли.
- Красный из-за чужой базовой линии: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch && python3 scripts/ui/ui_guard.py` — новые нарушения только в `WbProductPickerDialog.tsx`, `FfFbsOrdersScreen.tsx`, `FfFbsStockSyncScreen.tsx`, `FfFbsSupplyWorkspace.tsx`, `SellerInboundDraftScreen.tsx`; в затронутом `FbsSupplyCreateDialog.tsx` результат улучшился: `своя-кнопка 3 → 2`. Базовая линия не обновлялась.
- Не запустился из-за ограничения окружения: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend && npx playwright test tests-e2e/ff-fbs-supply.spec.ts --grep "fbs orders: create supply from selected orders"` — тестовый API не смог привязаться к `127.0.0.1:18000`, `operation not permitted`; сценарий не исполнялся.
- Зелёный: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend && git diff --check`.
- Не сохранено в Git из-за прав среды: точечный `git add` пяти файлов атома и `git commit -m "fix(fbs): show exact preflight source warehouses"` остановились на создании `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-1-04-warehouse-switch/index.lock` с `Operation not permitted`. Чужой `night/volna-9-recovery/JOURNAL.md` не добавлялся.

Полный backend `pytest`, `ruff check .` и `mypy .` не запускались согласно ограничению атомарной проверки.

## Не реализовано

- Буквально не подтверждён браузером целевой E2E-сценарий: запуск остановлен системным запретом bind до старта браузерного теста. Сам mock и видимые ожидания переведены на фактический серверный контракт `source_warehouse: null` + два элемента `source_warehouses[]`.
- Находка №2 из `REVIEW.md` относится к соседнему атому списка поставок S-03 и требует изменения `FfFbsOrdersScreen.tsx`, которого нет в файлах атома 9; она здесь не исправлялась. Находки №3–6 также относятся к другим экранам и слоям.
- Других пунктов контракта этого rework, которые не удалось реализовать буквально, нет.
- Отдельный commit SHA не получен из-за запрета записи в служебный Git-каталог worktree; изменения существуют только в рабочем дереве и требуют сохранения оркестратором.

## Находки

- Новых находок по данным, секретам или персональным данным нет.

# Фича 10

# Screen dev · 04-warehouse-switch · атом 10 · rework

Исправлена относящаяся к S-03 находка №2 из `REVIEW.md`: список поставок теперь запрашивается у сервера сразу с `warehouse_id` выбранного операционного WMS-склада. Лимит 500 применяется уже после складского фильтра, поэтому более старая поставка выбранного склада не пропадает из-за более свежих документов другого склада. До готовности WMS-контекста общий список поставок не запрашивается. Параметры WMS-поставок отделены от параметров WB-заказов, поэтому существующий фильтр склада селлера / WB не смешан с контекстом WMS.

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/FfFbsOrdersScreen.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/fbsApi.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/fbsApi.test.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/tests-e2e/ff-fbs-supply.spec.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/night/volna-9-recovery/cards/04-warehouse-switch/DEV.md`

## Гейты

- **Зелёный:** `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend && npx tsc --noEmit -p tsconfig.app.json`.
- **Зелёный:** `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend && npm run test:unit -- src/screens/v2/fbsApi.test.ts src/ui-kit/WarehouseContextSwitch.runner.test.ts` — 2 файла, 13 тестов прошли. Новый unit-кейс проверяет точный запрос `warehouse_id=warehouse-south`; suite общего переключателя из находки №6 реально исполнен и зелёный.
- **Красный на накопленном diff ветки:** `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch && python3 scripts/ui/ui_guard.py` — guard сообщает прежние монолиты `WbProductPickerDialog.tsx`, `FfFbsOrdersScreen.tsx`, `FfFbsStockSyncScreen.tsx`, `FfFbsSupplyWorkspace.tsx` и `SellerInboundDraftScreen.tsx`. Базовая линия флагом `--update` не менялась. Разделение монолита S-03 не входит в контракт атома и потребовало бы правки экранной архитектуры за пределами разрешённого поведения.
- **Зелёный, сценарий собран:** `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend && npx playwright test tests-e2e/ff-fbs-supply.spec.ts --grep "WMS warehouse context is sent to the server" --list` — найден 1 Chromium-тест. Он проверяет видимую замену поставки «Север» на поставку «Юг», серверные запросы `warehouse_id=w-1` и `warehouse_id=w-2` и отсутствие запроса без WMS-склада.
- **Не запустился из-за ограничения среды:** `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend && npx playwright test tests-e2e/ff-fbs-supply.spec.ts --grep "WMS warehouse context is sent to the server"` — Playwright webServer не получил право открыть `127.0.0.1:18000` (`Errno 1 operation not permitted`); браузерные шаги не исполнялись.
- **Зелёный:** `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch && git diff --check`.
- Полные backend `pytest`, `ruff check .` и `mypy .` не запускались согласно запрету атомарной проверки.

## Не реализовано

- Живое браузерное подтверждение нового сценария не получено: локальный API не смог привязаться к порту до старта теста.
- `ui_guard.py` не зелёный из-за накопленных превышений базовой линии в пяти экранах ветки. Baseline не обновлялся, а несвязанный архитектурный рефакторинг не выполнялся.
- Находки №1 и №3–5 из `REVIEW.md` относятся к другим атомам или слоям (`FbsSupplyCreateDialog`, S-14 и backend/seller) и в этом проходе не менялись. Находка №6 уже закрыта существующим runner-тестом ui-kit и подтверждена зелёными `tsc` и целевым unit-запуском.

## Находки

Секреты, ключи, токены, `.env`, кабинеты учётных данных и боевой прод `194.87.96.144` не открывались и не изменялись. Новых находок о данных или персональных данных в разрешённом frontend-слое нет.

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

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/fbsApi.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/FfFbsSupplyWorkspace.test.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/ui-kit/WarehouseContextSwitch.test.ts` — переименован из `WarehouseContextSwitch.test.tsx`, чтобы suite входил в маску Vitest `src/**/*.test.ts` и действительно исполнялся.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/night/volna-9-recovery/cards/04-warehouse-switch/DEV.md`

Чистая функция выбора заказа и ключа повтора `resolvePickScanAttempt` перенесена из экранного модуля в разрешённый `fbsApi.ts`. Поведение сканера не менялось; unit-тест больше не загружает весь экран вместе с модулем упаковки и исполняется без зависания на сборке зависимостей.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend` — зелёный.
- `python3 scripts/ui/ui_guard.py` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch` — красный на ранее накопленном превышении базовой линии: `WbProductPickerDialog.tsx` 0 → 646, `FfFbsOrdersScreen.tsx` 1587 → 1679, `FfFbsStockSyncScreen.tsx` 1083 → 1121, `FfFbsSupplyWorkspace.tsx` 2493 → 2604 и `SellerInboundDraftScreen.tsx` 1111 → 1267. Baseline флагом `--update` не изменялся. В этом проходе размер `FfFbsSupplyWorkspace.tsx` уменьшен на 15 строк.
- `npm run test:unit -- src/screens/v2/FfFbsSupplyWorkspace.test.ts src/ui-kit/WarehouseContextSwitch.test.ts` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend` — зелёный: 2 файла, 12 тестов.
- `npx eslint src/screens/v2/fbsApi.ts src/screens/v2/FfFbsSupplyWorkspace.tsx src/screens/v2/FfFbsSupplyWorkspace.test.ts src/ui-kit/WarehouseContextSwitch.test.ts tests-e2e/ff-fbs-supply.spec.ts` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend` — зелёный.
- `npx playwright test tests-e2e/ff-fbs-supply.spec.ts --grep 'scan location then product'` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend` — красный до запуска браузерного кейса: среда запретила API webServer привязать `127.0.0.1:18000` (`operation not permitted`).
- `git diff --check` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch` — зелёный.
- `git add ...` для файлов этого атома — красный: Git не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-1-04-warehouse-switch/index.lock` (`Operation not permitted`). Отдельный коммит в этой среде создать невозможно.

## Не реализовано

- Буквально не выполнен живой Playwright-прогон целевого сценария смены склада/ячейки и сетевого повтора: локальный API не смог открыть порт в этой среде. Сам сценарий сохранён в `frontend/tests-e2e/ff-fbs-supply.spec.ts`, а относящаяся к повтору чистая логика покрыта зелёными unit-тестами.
- `ui_guard.py` не доведён до зелёного: четыре из пяти нарушений находятся в соседних экранах вне файлов атома 12, а устранение оставшегося превышения потребовало бы несогласованного разбиения рабочего места на новые компоненты. Базовая линия намеренно не обновлялась.
- Находки REVIEW.md №1–5 не относятся к сканерному атому 12: это создание поставки, список поставок, упаковка, inbound API и серверное отображение ошибок. Они не исправлялись, чтобы не переходить к соседним атомам. Находка №6 исправлена в разрешённом тестовом слое: suite больше не зависит от отсутствующего пакета и теперь действительно запускается.
- Изменения локально реализованы, но не сохранены отдельным Git-коммитом из-за запрета записи в общий git-dir. До переноса/коммита из среды с доступом к `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-1-04-warehouse-switch` diff можно потерять.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных и боевой прод не читались и не изменялись.

# Фича 13

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/night/volna-9-recovery/cards/04-warehouse-switch/DEV.md`

Экранные файлы атома повторно проверены и не менялись. Уже реализованная frontend-логика
соответствует контракту: S-26 не содержит глобального складского переключателя; S-29 при двух
доступных операционных складах показывает только их имена, а при одном складе не показывает поле;
S-28 разрешает менять склад только в черновике и после передачи оставляет только текст документа.
Служебные `FBS WB *`, неоперационные склады и технические коды отфильтрованы. При ответе PATCH со
старым `warehouse_id` экран не показывает ложный успех, откатывает выбор и выводит понятную ошибку.

## Гейты

- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend && npx tsc --noEmit -p tsconfig.app.json` — зелёный, exit code 0.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch && python3 scripts/ui/ui_guard.py` — красный, exit code 1. Храповик сообщил ранее накопленные превышения: `src/components/WbProductPickerDialog.tsx` 0 → 646, `src/screens/v2/FfFbsOrdersScreen.tsx` 1587 → 1679, `src/screens/v2/FfFbsStockSyncScreen.tsx` 1083 → 1121, `src/screens/v2/FfFbsSupplyWorkspace.tsx` 2493 → 2605 и `src/screens/v2/SellerInboundDraftScreen.tsx` 1111 → 1267. Baseline флагом `--update` не изменялся.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend && npm run test:unit -- --run src/screens/v2/sellerInboundDocumentUi.test.ts` — зелёный: 1 test file, 9 tests passed.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend && npx playwright test tests-e2e/seller-cabinet.spec.ts --grep "admin creates seller user; seller sees filtered catalog and inbound"` — красный до старта браузера: тестовый API не смог привязать `127.0.0.1:18000`, среда вернула `[Errno 1] operation not permitted`; сценарий не исполнялся.

## Не реализовано

- Находка №4 из `REVIEW.md` не может быть исправлена буквально в роли `screen-dev`. Серверная схема `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/app/api/inbound_intake.py` не принимает `warehouse_id` в `InboundIntakeRequestPlannedPatch`, поэтому реальный API игнорирует отправленный экраном выбор. Исправление требует backend-файлов и backend-роли; они не входят в разрешённые файлы S-26/S-28/S-29 и не изменялись. Профильный E2E уже требует сохранения `warehouse_id` в ответе PATCH и после перезагрузки, поэтому не маскирует дефект.
- Живой браузерный сценарий не подтверждён из-за запрета среды на локальный порт. Условия одного и двух складов, фильтрация служебных/неоперационных складов, блокировка после передачи и проверка ответа PATCH покрыты зелёными unit-тестами.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных и боевой production не читались и не изменялись.
