# Technical Builder Plan

## Input

Used file:

`docs/analysis/01_normalized_process_spec.md` (решения владельца DEC-001…DEC-011 от 2026-06-27)

## Summary

- Что нужно сделать: привести процесс **отгрузки на маркетплейс** (`MarketplaceUnloadRequest`) к WB-подобной цепочке — план без общего подбора, вкладки «Товары / Упаковка / Короба / Финал», упаковка с create draft, обязательная упаковка до коробов, добавление товаров в конкретный короб (адресное хранение опционально), списание при добавлении в короб, массовое создание коробов, финал с печатью всех ШК.
- Какие части системы затронуты: домен `marketplace_unload`, `packaging_task`, `inventory_service`, UI `FfSuppliesShipmentsPage`, `FfSettingsScreen`, `FfInboundRequestView`, тесты.
- Главные риски: перенос списания с `ship_request` в `collect_into_box` + согласование резервов (DEC-006); зона сортировки vs ячейки при включении адресного хранения (DEC-005); крупный UI-рефакторинг dialog → вкладки.

## Code Context

### Домен «Отгрузка на МП» (marketplace unload)

- Файлы/модули:
  - `backend/app/models/marketplace_unload.py`
  - `backend/app/services/marketplace_unload_service.py`
  - `backend/app/services/marketplace_unload_pick_service.py`
  - `backend/app/services/marketplace_unload_collect_service.py`
  - `backend/app/services/marketplace_unload_box_service.py`
  - `backend/app/api/marketplace_unload_requests.py`
  - `frontend/src/screens/ff/FfSuppliesShipmentsPage.tsx`
  - `frontend/src/components/SellerMarketplaceUnloadDialog.tsx`
- Что уже есть: документ отгрузки со статусами draft → submitted → confirmed → shipped; строки плана; короба и строки коробов; pick allocations; API pick-options / pick-allocations / pick/scan; сборка через `collect_into_box`; ship с `apply_marketplace_unload_pick`; UI с `ff-mp-boxes`, `ff-mp-start-picking`, `ff-mp-picking-dialog`, счётчик `mpCollectSummary`.
- Как использовать текущий паттерн: бизнес-логика в `*_service.py`, тонкие роуты в `marketplace_unload_requests.py`, UI через `data-testid` и MUI-компоненты как в текущем `FfSuppliesShipmentsPage.tsx`.
- Статус: **PARTIAL**

### Операционная отгрузка (outbound shipment — не целевой контур)

- Файлы/модули:
  - `backend/app/models/outbound_shipment.py`
  - `backend/app/services/outbound_shipment_service.py`
  - `backend/app/api/outbound_shipment.py`
  - `frontend/src/screens/v2/OutboundScreen.tsx`
- Что уже есть: отдельный процесс списания остатков без коробов и упаковки WB-like.
- Как использовать текущий паттерн: не трогать; только не смешивать терминологию и scope (Assumption A-001).
- Статус: **EXISTS** (вне scope изменений)

### Адресное хранение (глобальный переключатель ФФ)

- Файлы/модули:
  - `NOT_FOUND` (флаг/настройка tenant)
  - `backend/app/models/tenant.py`
  - `backend/app/models/storage_location.py`
  - `backend/app/models/warehouse.py`
  - `backend/app/models/warehouse_storage_rack.py`
  - `frontend/src/screens/ff/FfSettingsScreen.tsx`
  - `frontend/src/screens/ff/FfInboundRequestView.tsx`
- Что уже есть: инфраструктура складов/ячеек; `collect_into_box` и `scan_barcode_into_box` всегда требуют `storage_location_id`; UI настроек ФФ — только staff/permissions, без tenant-флагов.
- Как использовать текущий паттерн: расширить `Tenant` + Alembic migration; чтение флага в сервисах collect/pick; checkbox в `FfSettingsScreen` по аналогии с существующими формами.
- Статус: **MISSING** (настройка); **EXISTS** (инфраструктура ячеек)

### Упаковка, связанная с отгрузкой

- Файлы/модули:
  - `backend/app/models/packaging_task.py`
  - `backend/app/services/packaging_task_service.py`
  - `backend/app/api/packaging_tasks.py`
  - `frontend/src/screens/ff/FfPackagingPage.tsx` (`FfPackagingTaskPanel`, `FfPackagingTaskDialog`)
- Что уже есть: `ensure_task_for_unload` вызывается из `confirm_request` в `marketplace_unload_service.py`; авто-переход в `done` через `_touch_task` / `is_task_complete`; `assert_unload_packaging_done` только в `ship_request`; ЧЗ и этикетки через `FfPackagingTaskPanel` и `backend/app/api/marking_codes.py`.
- Как использовать текущий паттерн: явный endpoint «завершить упаковку» рядом с существующими операциями строк; UI — встроить `FfPackagingTaskPanel` во вкладку, не дублировать логику ЧЗ.
- Статус: **PARTIAL**

### Короба и добавление товаров

- Файлы/модули:
  - `backend/app/models/warehouse_box.py`
  - `backend/app/services/marketplace_unload_box_service.py`
  - `backend/app/services/marketplace_unload_collect_service.py`
  - `frontend/src/screens/ff/FfSuppliesShipmentsPage.tsx` (`data-testid="ff-mp-boxes"`)
  - `frontend/src/components/ProductPhotoThumb.tsx`
- Что уже есть: `create_open_box` с ограничением `open_box_exists`; пресеты коробов; `scan_barcode_into_box`, `add_manual_qty_to_box`, `close_box`, `attach_existing_box_by_barcode`; inline scan в UI; `ProductPhotoThumb` не используется в блоке коробов.
- Как использовать текущий паттерн: расширить `marketplace_unload_box_service.py` новыми операциями; API роуты рядом с `POST /{request_id}/boxes`; UI-модалка — отдельный компонент с `data-testid`, фото через `ProductPhotoThumb`.
- Статус: **PARTIAL**

### Общий подбор («Начать подбор»)

- Файлы/модули:
  - `frontend/src/screens/ff/FfSuppliesShipmentsPage.tsx` (`ff-mp-start-picking`, `ff-mp-picking-dialog`)
  - `backend/app/api/marketplace_unload_requests.py` (`pick-options`, `pick-allocations`, `PUT pick-allocations`)
  - `backend/app/services/marketplace_unload_pick_service.py` (`save_pick_allocations`, `get_pick_options`)
- Что уже есть: отдельная модалка ручного подбора; allocations как промежуточное состояние до коробов.
- Как использовать текущий паттерн: убрать UI и ручной save; оставить allocations только как побочный эффект `collect_into_box` (если модель данных сохраняется).
- Статус: **CONFLICT**

### Списание со склада / ячеек

- Файлы/модули:
  - `backend/app/services/marketplace_unload_collect_service.py` (`collect_into_box`)
  - `backend/app/services/marketplace_unload_pick_service.py` (`ship_request`)
  - `backend/app/services/inventory_service.py` (`apply_marketplace_unload_pick`, `available_at_location`)
- Что уже есть: при сборке проверяется `available_at_location`, но движение остатков — только в `ship_request`; резервы при `confirm_request`.
- Как использовать текущий паттерн: вызов `apply_marketplace_unload_pick` (или выделенной функции) из `collect_into_box`; в `ship_request` убрать повторное списание, оставить финальные проверки и смену статуса.
- Статус: **CONFLICT**

### UI: вкладки, модалка короба, финальный шаг

- Файлы/модули:
  - `frontend/src/screens/ff/FfSuppliesShipmentsPage.tsx`
  - `frontend/src/components/ProductPhotoThumb.tsx`
  - `frontend/src/components/WbProductPickerDialog.tsx`
- Что уже есть: один modal документа; упаковка через `FfPackagingTaskDialog`; финал — кнопка ship + `planned_shipment_date` + `wb_mp_warehouse_id`; полей водитель/авто/пропуск в `MarketplaceUnloadRequest` нет.
- Как использовать текущий паттерн: MUI Tabs внутри modal/detail; эталон структуры — другие FF-экраны с вкладками; поля финала — patch API + форма на вкладке «Финал».
- Статус: **PARTIAL** / **MISSING** (отдельные элементы)

### Тесты

- Файлы/модули:
  - `backend/tests/test_marketplace_unload_and_discrepancy_acts.py`
  - `backend/tests/test_seller_marketplace_unload.py`
  - `frontend/tests-e2e/ff-mp-ship-pick.spec.ts`
  - `frontend/tests-e2e/seller-mp-unload.spec.ts`
  - `frontend/tests-e2e/ff-mp-print-waybill.spec.ts`
- Что уже есть: backend-тесты отгрузки и расхождений; e2e сценарий «pick by cell and ship reduces stock» (списание на ship).
- Как использовать текущий паттерн: обновить ожидания под новый момент списания; добавить TC-ID в комментарии e2e; pytest зеркалит сервисы.
- Статус: **PARTIAL**

## Scope

### In Scope

- Все REQ-001 … REQ-014 для контура `marketplace_unload` (DEC-001).
- Решения DEC-001 … DEC-011 из spec (см. таблицу Decisions).
- Глобальная настройка адресного хранения, дефолт **вкл.** (REQ-001, DEC-009).
- Удаление UI/API общего подбора (REQ-003).
- Упаковка: create draft, sync строк, вкладка, complete, блокировка коробов (REQ-004–006, DEC-003, DEC-008).
- Короба: batch create, per-box modal, меню короба (REQ-007, REQ-008, REQ-010, DEC-007).
- Списание при добавлении в короб; агрегированный остаток или ячейка/зона сортировки (REQ-009, DEC-005, DEC-006).
- Счётчики, предупреждения, пустые короба при ship (REQ-011, DEC-002, DEC-010).
- Финал: дата МП, склад МП, «Печать всех ШК», проверки (REQ-012, DEC-004, DEC-011) — **без** полей водитель/авто/пропуск.
- API-контракт ТСД (REQ-014).
- Backend pytest и Playwright e2e.

### Out of Scope

- `OutboundShipmentRequest` и `OutboundScreen.tsx` (DEC-001).
- Поля финала: водитель, автомобиль, пропуск, способ перевозки (DEC-004).
- Мобильный/Android клиент (REQ-014 — только API-контракт).
- Импорт товаров сверх `WbProductPickerDialog` (A-003).
- Отдельная сущность «магазин» вместо `Seller` (A-002).
- Полная переработка приёмки — только скрытие ячеек при выкл. адресном хранении (REQ-001).

## Builder Tasks

### TASK-001. Tenant-флаг «Адресное хранение» (data + API + настройки ФФ)

- Статус: **READY**
- Тип изменения: Data / Backend / API / UI / Permissions
- Связанные требования: REQ-001, BR-006, Step 6, GAP-001
- Цель: глобальный переключатель ФФ, доступный сервисам и UI.
- Файлы/модули:
  - `backend/app/models/tenant.py`
  - `backend/alembic/versions/` (новая migration)
  - `NOT_FOUND` (отдельный `tenant_settings` service — создать или расширить существующий паттерн через model + API)
  - `backend/app/api/` (endpoint чтения/обновления настройки tenant для admin)
  - `frontend/src/screens/ff/FfSettingsScreen.tsx`
- Шаги реализации:
  1. Добавить boolean-поле на `Tenant` (имя согласовать с доменным языком репозитория) через Alembic autogenerate.
  2. Реализовать чтение/обновление флага в service-слое с проверкой роли admin.
  3. Expose GET/PATCH (или PATCH tenant) в `backend/app/api`.
  4. Добавить checkbox на `FfSettingsScreen` с сохранением и отображением текущего значения.
  5. Прокинуть значение флага в auth/me или отдельный lightweight endpoint для UI отгрузки/приёмки.
- Критерии готовности:
  - Admin может включить/выключить флаг; значение persists после reload.
  - **Дефолт: адресное хранение включено** (DEC-009).
- Проверки:
  - `pytest` на API настройки.
  - Ручная: toggling в `ff-settings-screen`.
- Зависимости:
  - нет
- Блокеры:
  - нет

### TASK-002. Условная обязательность ячеек в collect/pick API

- Статус: **READY**
- Тип изменения: Backend / API / Errors
- Связанные требования: REQ-001, REQ-009, BR-004, BR-006
- Цель: при выкл. — collect без ячейки, списание с агрегированного остатка; при вкл. — ячейка или зона сортировки (DEC-005).
- Файлы/модули:
  - `backend/app/services/marketplace_unload_collect_service.py`
  - `backend/app/services/marketplace_unload_box_service.py`
  - `backend/app/services/marketplace_unload_pick_service.py`
  - `backend/app/services/inventory_service.py`
  - `backend/app/api/marketplace_unload_requests.py`
- Шаги реализации:
  1. Централизовать `is_address_storage_enabled(tenant_id)` в service (single path rule).
  2. **Выкл. (DEC-005):** `storage_location_id` optional; списание через существующие методы агрегированного остатка в `inventory_service` (без inventing новых сущностей).
  3. **Вкл.:** обязательна ячейка **или** зона сортировки, если товар ещё не разложен по ячейкам.
  4. Обновить схемы request body в API.
  5. Scan-порядок ячейка→товар при вкл. флаге (REQ-014).
- Критерии готовности:
  - При выкл. флаге POST scan/manual-line успешен без location.
  - При вкл. — ошибка без location; с location — как сейчас.
- Проверки:
  - pytest: оба режима флага.
- Зависимости:
  - TASK-001
- Блокеры:
  - нет

### TASK-003. Скрытие UI ячеек в отгрузке и приёмке при выкл. флаге

- Статус: **READY**
- Тип изменения: UI
- Связанные требования: REQ-001
- Цель: пользователь не видит scan/поля ячеек, когда адресное хранение выключено.
- Файлы/модули:
  - `frontend/src/screens/ff/FfSuppliesShipmentsPage.tsx`
  - `frontend/src/screens/ff/FfInboundRequestView.tsx`
- Шаги реализации:
  1. Загрузить tenant-флаг в экраны (из TASK-001 endpoint).
  2. Скрыть `ff-mp-active-location`, picking location columns, inbound cell UI при `false`.
  3. Не ломать существующие `data-testid` при вкл. флаге.
- Критерии готовности:
  - При выкл. — нет видимых полей ячеек на отгрузке и в затронутых блоках приёмки.
- Проверки:
  - Playwright smoke или manual UI proof.
- Зависимости:
  - TASK-001, TASK-002
- Блокеры:
  - нет

### TASK-004. Списание остатков при добавлении в короб (не на ship)

- Статус: **READY**
- Тип изменения: Backend / Errors
- Связанные требования: REQ-009, BR-004, GAP-002
- Цель: списание в `collect_into_box`; резерв при confirm сохраняется; ship без повторного movement (DEC-006).
- Файлы/модули:
  - `backend/app/services/marketplace_unload_collect_service.py`
  - `backend/app/services/marketplace_unload_pick_service.py` (`ship_request`)
  - `backend/app/services/inventory_service.py`
  - `backend/app/services/marketplace_unload_service.py` (резервы при confirm)
- Шаги реализации:
  1. После валидации в `collect_into_box` вызвать движение остатков (`apply_marketplace_unload_pick` или эквивалент для агрегированного режима).
  2. Согласовать резерв при confirm с частичным списанием при сборке в короба.
  3. В `ship_request` убрать повторный inventory movement; добавить удаление **пустых коробов** (DEC-002).
  4. При удалении товара из короба (TASK-010) — откат списания на тот же источник (ячейка/агрегат).
- Критерии готовности:
  - После add в короб `available_at_location` уменьшается без ship.
  - Ship не создаёт второго движения.
- Проверки:
  - pytest collect + inventory balance.
  - Обновить `ff-mp-ship-pick.spec.ts` ожидание момента списания.
- Зависимости:
  - TASK-002 (для режима без ячеек)
- Блокеры:
  - нет

### TASK-005. Удаление этапа «общий подбор в документ»

- Статус: **READY**
- Тип изменения: UI / API / Backend
- Связанные требования: REQ-003, BR-002, GAP-003
- Цель: убрать отдельный подбор; allocations только через короба.
- Файлы/модули:
  - `frontend/src/screens/ff/FfSuppliesShipmentsPage.tsx` (`ff-mp-start-picking`, `ff-mp-picking-dialog`)
  - `backend/app/api/marketplace_unload_requests.py` (ручной `PUT pick-allocations` — deprecate или admin-only)
  - `backend/app/services/marketplace_unload_pick_service.py`
- Шаги реализации:
  1. Удалить кнопку и модалку «Начать подбор» из UI.
  2. Убрать отображение блока «подобрано в отгрузку» как отдельного этапа (см. TASK-011).
  3. Оставить или ограничить API `pick-options` только для модалки короба (не standalone picking).
  4. Обновить backend-тесты, завязанные на manual pick save.
- Критерии готовности:
  - В UI нет `ff-mp-start-picking`.
  - Добавление товара возможно только через короб (после упаковки).
- Проверки:
  - e2e: сценарий без picking dialog.
  - pytest API.
- Зависимости:
  - TASK-008 (блокировка коробов до упаковки)
- Блокеры:
  - нет

### TASK-006. Автосоздание PackagingTask при создании черновика отгрузки

- Статус: **READY**
- Тип изменения: Backend
- Связанные требования: REQ-004, Step 1, GAP-008, DEC-003, DEC-008
- Цель: связанный документ упаковки существует в draft; строки sync из плана при CRUD линий.
- Файлы/модули:
  - `backend/app/services/marketplace_unload_service.py` (`create_request`, add/delete line)
  - `backend/app/services/packaging_task_service.py` (`ensure_task_for_unload`, новая sync из `MarketplaceUnloadLine`)
  - `backend/app/api/marketplace_unload_requests.py`
- Шаги реализации:
  1. Вызвать `ensure_task_for_unload` из `create_request` (DEC-003).
  2. Sync строк упаковки из `MarketplaceUnloadLine` при add/update/delete line (DEC-008, BR-010).
  3. В `confirm_request` не создавать дубликат задачи.
  4. Detail API: `linked_packaging_task` доступен в draft.
- Критерии готовности:
  - Сразу после create видна связанная упаковка; изменение плана обновляет упаковку.
- Проверки:
  - pytest create → packaging exists; add line → packaging line sync.
- Зависимости:
  - нет
- Блокеры:
  - нет

### TASK-007. Явное завершение упаковки (галочка + кнопка + lock)

- Статус: **READY**
- Тип изменения: Backend / API / UI
- Связанные требования: REQ-005, BR-007, Step 4
- Цель: оператор явно завершает упаковку; после `done` — read-only; авто-done через `_touch_task` не единственный путь.
- Файлы/модули:
  - `backend/app/services/packaging_task_service.py`
  - `backend/app/api/packaging_tasks.py`
  - `frontend/src/screens/ff/FfPackagingPage.tsx` (`FfPackagingTaskPanel`)
  - `frontend/src/screens/ff/FfSuppliesShipmentsPage.tsx`
- Шаги реализации:
  1. Endpoint «complete packaging» с опциональной галочкой «весь товар упакован» (business rules из spec, без новых полей вне spec).
  2. При complete: status=done, запрет дальнейших правок строк.
  3. UI: checkbox + кнопка «Завершить упаковку»; после done — disabled controls.
  4. Сохранить ЧЗ/этикетки из `FfPackagingTaskPanel` (REQ-013).
- Критерии готовности:
  - Оператор завершает упаковку одной кнопкой; повторное редактирование блокируется.
- Проверки:
  - pytest complete; UI read-only state.
- Зависимости:
  - TASK-006
- Блокеры:
  - нет

### TASK-008. Блокировка операций с коробами до завершения упаковки

- Статус: **READY**
- Тип изменения: Backend / API / UI / Errors
- Связанные требования: REQ-006, BR-003, GAP-004
- Цель: `collect_into_box`, create/attach box возвращают `packaging_not_done` до done упаковки; UI показывает «Сначала завершите упаковку товара».
- Файлы/модули:
  - `backend/app/services/packaging_task_service.py` (`assert_unload_packaging_done`)
  - `backend/app/services/marketplace_unload_collect_service.py`
  - `backend/app/services/marketplace_unload_box_service.py`
  - `backend/app/api/marketplace_unload_requests.py`
  - `frontend/src/screens/ff/FfSuppliesShipmentsPage.tsx`
- Шаги реализации:
  1. Вынести проверку упаковки в shared helper; вызывать в collect/create box paths (не только ship).
  2. Маппинг ошибки в API и блокирующий Alert/Dialog в UI.
- Критерии готовности:
  - Попытка add в короб при незавершённой упаковке блокируется с текстом из spec.
- Проверки:
  - pytest + e2e negative path.
- Зависимости:
  - TASK-007
- Блокеры:
  - нет

### TASK-009. Массовое создание N коробов

- Статус: **READY**
- Тип изменения: Backend / API / UI
- Связанные требования: REQ-007, Step 5, GAP-006
- Цель: «Создать короба» + N → N записей `MarketplaceUnloadBox`; снять ограничение `open_box_exists` для batch-сценария.
- Файлы/модули:
  - `backend/app/services/marketplace_unload_box_service.py`
  - `backend/app/api/marketplace_unload_requests.py`
  - `frontend/src/screens/ff/FfSuppliesShipmentsPage.tsx`
- Шаги реализации:
  1. Service `create_boxes_batch(request_id, count, preset)` с проверкой упаковки (TASK-008).
  2. API POST batch (новый route или расширение body с `count`).
  3. UI: поле количества + кнопка; список всех коробов без концепции единственного «активного».
  4. Пересмотреть `get_open_box` / `require_open_box` для работы с явным `box_id`.
- Критерии готовности:
  - N коробов создаются одним действием; каждый имеет ШК.
- Проверки:
  - pytest batch create.
- Зависимости:
  - TASK-008
- Блокеры:
  - нет

### TASK-010. Действия короба: печать ШК, копия, удаление

- Статус: **READY**
- Тип изменения: Backend / API / UI
- Связанные требования: REQ-010, Step 7
- Цель: delete только пустой короб; copy в новый короб; print ШК (DEC-007).
- Файлы/модули:
  - `backend/app/services/marketplace_unload_box_service.py`
  - `backend/app/api/marketplace_unload_requests.py`
  - `NOT_FOUND` (copy box / delete box / remove line from box service functions)
  - `frontend/src/screens/ff/FfSuppliesShipmentsPage.tsx`
- Шаги реализации:
  1. **Remove line from box:** уменьшить qty, откат списания (связано с TASK-004).
  2. **Delete box:** только если все lines qty=0 (DEC-007).
  3. **Copy to new box:** duplicate lines в новый `MarketplaceUnloadBox` без превышения плана (BR-005).
  4. Print barcode: reuse flow для `warehouse_boxes.internal_barcode`.
  5. UI: row action menu с `data-testid`.
- Критерии готовности:
  - Delete блокируется при qty>0; после очистки короба — delete OK; copy в пределах плана.
- Проверки:
  - pytest copy/delete; manual print.
- Зависимости:
  - TASK-004, TASK-009
- Блокеры:
  - нет

### TASK-011. Модалка «Добавить товары» напротив короба

- Статус: **READY**
- Тип изменения: UI / API
- Связанные требования: REQ-008, Step 6, REQ-014
- Цель: большая модалка с фото, план/распределено/доступно, scan и ручной ввод, лимит по плану.
- Файлы/модули:
  - `frontend/src/screens/ff/FfSuppliesShipmentsPage.tsx`
  - `NOT_FOUND` (выделенный компонент модалки — создать рядом с screens/ff)
  - `frontend/src/components/ProductPhotoThumb.tsx`
  - `backend/app/api/marketplace_unload_requests.py` (существующие scan/manual-line)
- Шаги реализации:
  1. Кнопка «Добавить товары» на каждой строке короба.
  2. Модалка: таблица товаров плана с counters; scan location (условно) + product; manual qty.
  3. Использовать `ProductPhotoThumb` с hover-zoom.
  4. Блокировать qty above plan (BR-005).
- Критерии готовности:
  - Модалка открывается из строки короба; нельзя превысить план.
- Проверки:
  - e2e add via modal; pytest лимиты.
- Зависимости:
  - TASK-002, TASK-004, TASK-008, TASK-009
- Блокеры:
  - нет

### TASK-012. Вкладочная структура документа отгрузки

- Статус: **READY**
- Тип изменения: UI
- Связанные требования: REQ-004, REQ-012 (layout), GAP-005
- Цель: вкладки «Товары / Упаковка / Короба / Финальная отгрузка» внутри одного документа вместо разрозненных dialogs.
- Файлы/модули:
  - `frontend/src/screens/ff/FfSuppliesShipmentsPage.tsx`
  - `frontend/src/screens/ff/FfPackagingPage.tsx` (`FfPackagingTaskPanel`)
  - `frontend/src/components/SellerMarketplaceUnloadDialog.tsx` (seller flow — согласовать parity)
- Шаги реализации:
  1. MUI Tabs с `data-testid` на каждой вкладке.
  2. Вкладка «Товары»: план, seller, add products (REQ-002 EXISTS).
  3. Вкладка «Упаковка»: embed `FfPackagingTaskPanel` + complete controls (TASK-007).
  4. Вкладка «Короба»: batch create, список, modal add (TASK-009, TASK-011).
  5. Вкладка «Финал»: дата МП, склад МП, «Печать всех ШК», ship (TASK-014); disabled если распределение неполное.
  6. Убрать standalone `FfPackagingTaskDialog` для этого flow или оставить только deep-link fallback.
- Критерии готовности:
  - Пользователь переключает вкладки без потери контекста документа.
- Проверки:
  - Playwright navigation across tabs; `admin-shell-layout` не ломается.
- Зависимости:
  - TASK-007, TASK-009, TASK-011
- Блокеры:
  - нет

### TASK-013. Счётчики плана, распределения и упаковки

- Статус: **READY**
- Тип изменения: UI / Backend
- Связанные требования: REQ-011, BR-008, DEC-010
- Цель: подписи «план отгрузки», «распределено по коробам», «остаток», статус упаковки; предупреждение при неполном распределении; убрать «Собрано» как счётчик общего подбора.
- Файлы/модули:
  - `frontend/src/screens/ff/FfSuppliesShipmentsPage.tsx` (`mpCollectSummary`, `ff-mp-collect-summary`)
  - `backend/app/services/marketplace_unload_collect_service.py` (`picked_qty_by_product`)
- Шаги реализации:
  1. Переименовать/пересчитать `mpCollectSummary`: planned / distributed / remaining.
  2. Добавить отображение packaging status рядом со счётчиками.
  3. **Предупреждение** на вкладке «Короба», если распределено < плана (DEC-010, BR-008).
  4. Удалить UX «подобрано в отгрузку» (TASK-005).
- Критерии готовности:
  - Счётчики соответствуют spec; нет отдельного pick-to-document counter.
- Проверки:
  - e2e asserts on summary testids.
- Зависимости:
  - TASK-005, TASK-011
- Блокеры:
  - нет

### TASK-014. Вкладка «Финальная отгрузка» (без полей перевозки)

- Статус: **READY**
- Тип изменения: UI / Backend / Errors
- Связанные требования: REQ-012, Step 8, DEC-004, DEC-010, DEC-011, DEC-002
- Цель: вкладка «Финал» с датой МП, складом МП, кнопкой «Печать всех ШК», проверками перед ship; **без** новых полей модели (водитель/авто/пропуск — out of scope).
- Файлы/модули:
  - `backend/app/services/marketplace_unload_pick_service.py` (`ship_request`)
  - `backend/app/api/marketplace_unload_requests.py`
  - `frontend/src/screens/ff/FfSuppliesShipmentsPage.tsx`
  - `frontend/src/utils/printShipmentWaybill.py` (или аналог print для box barcodes)
- Шаги реализации:
  1. Вкладка «Финал»: существующие поля `planned_shipment_date`, `wb_mp_warehouse_id`.
  2. Кнопка **«Печать всех ШК коробов»** (DEC-011).
  3. `ship_request`: проверка полного распределения (DEC-010); предупреждение UI на вкладке «Короба» и при ship.
  4. При ship: auto-delete **пустых** коробов (DEC-002); убрать `acknowledge_discrepancy` для partial qty (ship только при X=Y).
  5. Ship без повторного inventory movement (после TASK-004).
- Критерии готовности:
  - Ship блокируется, если распределено < плана; пустые короба исчезают после ship.
- Проверки:
  - pytest ship validation; e2e final tab + print all barcodes.
- Зависимости:
  - TASK-012, TASK-013, TASK-004
- Блокеры:
  - нет

### TASK-015. Рефактор ship_request после переноса списания

- Статус: **READY**
- Тип изменения: Backend / Errors
- Связанные требования: REQ-009, REQ-012, BR-008
- Цель: финальный ship — проверки и смена статуса без повторного inventory movement.
- Файлы/модули:
  - `backend/app/services/marketplace_unload_pick_service.py`
  - `backend/app/services/marketplace_unload_service.py` (`release_reservations_for_shipped`)
- Шаги реализации:
  1. Удалить цикл `apply_marketplace_unload_pick` из ship (после TASK-004).
  2. Сохранить проверки: packaging done, planned date, wb warehouse, полное распределение (DEC-010).
  3. Auto-delete пустых коробов при ship (DEC-002).
  4. Убрать `acknowledge_discrepancy` для partial quantity — ship только при полном распределении.
- Критерии готовности:
  - Ship идempotent по inventory; статус shipped; пустые короба удалены.
- Проверки:
  - pytest ship; regression empty box cleanup.
- Зависимости:
  - TASK-004
- Блокеры:
  - нет

### TASK-016. Backend tests marketplace unload

- Статус: **READY**
- Тип изменения: Tests
- Связанные требования: все backend-затронутые REQ
- Цель: pytest покрывает новые правила (packaging gate, batch boxes, collect inventory, tenant flag).
- Файлы/модули:
  - `backend/tests/test_marketplace_unload_and_discrepancy_acts.py`
  - `backend/tests/test_seller_marketplace_unload.py`
  - `NOT_FOUND` (отдельный test module для packaging+boxes — создать при необходимости)
- Шаги реализации:
  1. Добавить кейсы на TASK-002, TASK-004, TASK-008, TASK-009.
  2. Обновить/удалить тесты manual pick allocations.
  3. `ruff check . && mypy . && pytest` green.
- Критерии готовности:
  - Все новые business rules имеют failing-before/passing-after tests.
- Проверки:
  - локальный pytest в `backend/`.
- Зависимости:
  - соответствующие feature tasks
- Блокеры:
  - нет

### TASK-017. E2E tests отгрузки на МП

- Статус: **READY**
- Тип изменения: Tests
- Связанные требования: REQ-003, REQ-006, REQ-008, REQ-009, TC traceability
- Цель: Playwright сценарии с TC-ID в title/comment; user-visible outcomes.
- Файлы/модули:
  - `frontend/tests-e2e/ff-mp-ship-pick.spec.ts`
  - `frontend/tests-e2e/seller-mp-unload.spec.ts`
  - `frontend/tests-e2e/ff-mp-print-waybill.spec.ts`
- Шаги реализации:
  1. Обновить happy path: упаковка → короба → modal add → ship.
  2. Negative: add to box before packaging complete.
  3. Указать TC-NEW-* или TC-S* в комментариях тестов.
  4. `npm run test:e2e` green (workers:1).
- Критерии готовности:
  - E2E отражает новый порядок шагов spec.
- Проверки:
  - `npm run build && npm run test:e2e` в `frontend/`.
- Зависимости:
  - TASK-008, TASK-011, TASK-012
- Блокеры:
  - нет

### TASK-018. API-контракт scan-потока для ТСД

- Статус: **READY**
- Тип изменения: API / Errors
- Связанные требования: REQ-014, Step 6
- Цель: стабильный порядок scan endpoints и коды ошибок для будущего Android; без нового мобильного клиента.
- Файлы/модули:
  - `backend/app/api/marketplace_unload_requests.py`
  - `NOT_FOUND` (отдельный markdown API doc — только если уже есть канон в repo; иначе docstring/OpenAPI descriptions)
- Шаги реализации:
  1. Зафиксировать sequence: (optional location scan) → product scan → box line update для `POST .../boxes/{id}/scan`.
  2. Единые error codes: `packaging_not_done`, `plan_limit_exceeded`, `location_required`.
  3. Не ломать существующие paths (`pick/scan` — deprecate или alias для TSD).
- Критерии готовности:
  - Документированный контракт в PR/issue notes; endpoints unchanged breaking for web.
- Проверки:
  - pytest contract smoke; manual curl sequence.
- Зависимости:
  - TASK-002, TASK-011
- Блокеры:
  - нет

## Implementation Order

1. **TASK-001** — флаг адресного хранения (DEC-009 default on).
2. **TASK-006** — упаковка при create draft + sync строк (DEC-003, DEC-008).
3. **TASK-002** — collect без/с ячейкой, зона сортировки (DEC-005).
4. **TASK-003** — скрытие UI ячеек.
5. **TASK-007** — завершение упаковки.
6. **TASK-008** — gate коробов на упаковку.
7. **TASK-004** — списание при collect (DEC-006) — **до TASK-010 и TASK-011**.
8. **TASK-009** — batch короба.
9. **TASK-010** — меню короба, remove line, delete empty (DEC-007).
10. **TASK-011** — модалка добавления в короб.
11. **TASK-005** — удаление «Начать подбор».
12. **TASK-013** — счётчики + предупреждения (DEC-010).
13. **TASK-012** — вкладочный UI.
14. **TASK-015** — refactor ship.
15. **TASK-014** — финал + print all ШК (DEC-011).
16. **TASK-016**, **TASK-017** — тесты по блокам; финальный CI.
17. **TASK-018** — API-контракт ТСД.

## Test Plan

### Unit

- Tenant flag read/write; default value.
- `collect_into_box`: with/without location; plan limit; packaging_not_done.
- `create_boxes_batch`: N boxes; rejects when packaging incomplete.
- `complete_packaging`: done locks edits; assert_unload_packaging_done passes.
- Inventory: single movement on collect; no double on ship.
- Box delete only when empty; remove line reverses collect.
- Empty boxes purged on ship.
- Warnings when distributed < planned (boxes tab + ship).

### Integration

- Create unload → packaging in draft → sync lines → complete packaging → batch boxes → add lines → ship full flow API.
- Seller create flow — seller_id fixed (REQ-002).
- Address storage off: collect without location, aggregate stock.

### UI / Manual

- Tabs: products → packaging → boxes → final.
- Block message «Сначала завершите упаковку товара» on box add.
- Warning on boxes tab when distributed < planned (DEC-010).
- «Печать всех ШК» on final tab (DEC-011).

### Regression

- `backend/tests/test_marketplace_unload_and_discrepancy_acts.py`
- `backend/tests/test_seller_marketplace_unload.py`
- `frontend/tests-e2e/ff-mp-ship-pick.spec.ts`
- `frontend/tests-e2e/seller-mp-unload.spec.ts`
- `frontend/tests-e2e/ff-mp-print-waybill.spec.ts`
- Packaging ЧЗ/labels via `FfPackagingTaskPanel` (REQ-013)

## Stop Conditions

Builder должен остановиться, если:

- файл или модуль из задачи не найден;
- текущий код противоречит плану;
- нужна бизнес-логика, которой нет во входном файле;
- задача выходит за scope;
- критерии готовности нельзя проверить;
- связанное требование имеет статус `CONFLICT` и задача не описывает явное разрешение;
- связанное требование имеет статус `UNKNOWN` и без уточнения нельзя безопасно реализовать задачу;
- попытка реализовать изменения в `outbound_shipment` вместо `marketplace_unload` (DEC-001);
- попытка добавить поля водитель/авто/пропуск (DEC-004 out of scope).

---

## Review-04: обязательные правки задач (перекрывают разделы выше)

Источник: `04_independent_review_RU.md` + Decisions v2 (`01_normalized_process_spec.md`, DEC-012…020).
Применять **вместе** с задачами выше. Builder обязан учитывать эти дельты.

### Δ TASK-004 (списание) — расширить (DEC-016, DEC-017)
- Реализовать **инвентарный леджер**: confirm `reserved+=plan`; `collect_into_box` `reserved-=q, on_hand-=q` **в одной транзакции**; remove-from-box — обратный откат на тот же источник (ячейка/зона/агрегат).
- Списание **под блокировкой**: `SELECT … FOR UPDATE` строки остатка ячейки/агрегата + перепроверка под локом, либо `UPDATE … WHERE available >= q` с проверкой rowcount. **Тест на параллельную выдачу из одного источника** (без ухода в минус).

### Δ TASK-001 / TASK-002 — конкретизировать (DEC-018, DEC-019)
- TASK-002: «зона сортировки» = виртуальная `StorageLocation` приёмки (не новая сущность).
- TASK-001: toggle флага **блокируется**, если на ячейках есть остаток.

### Δ TASK-006 / TASK-007 — упаковка (DEC-013, DEC-014)
- TASK-006: правка строк плана после `done` упаковки → **сброс `done` и пере-синк** состава упаковки.
- TASK-007: «Завершить упаковку» (в т.ч. по галочке «Весь товар упакован») **валидирует ЧЗ** — для строк `requires_honest_sign` коды должны быть в системе; иначе блок. Переиспользовать существующий gate `assert_packaging_line_marking_done`, не вводить обход. Отключить единственный авто-`done` через `_touch_task`, чтобы завершение было явным.

### Δ TASK-011 — модалка короба (DEC-020)
- «Доступно к добавлению» = **`min(остаток плана, физически доступно/по ячейке)`**, а не только план.

### Δ TASK-013 / TASK-014 / TASK-015 — финал и недопоставка (DEC-012)
- Предупреждение при `распределено < план` остаётся; **ship разрешён с явным подтверждением недопоставки**. Не блокировать ship намертво. `acknowledge_discrepancy` **не удалять** — переиспользовать как подтверждение недопоставки (пометить факт < план).

### TASK-019 (НОВАЯ). Отмена/abandon отгрузки → откат инвентаря
- **Статус:** READY. **Тип:** Backend / Errors. **Треб.:** DEC-016, BR-013.
- Цель: при отмене отгрузки до ship — вернуть весь `on_hand`, лежащий в коробах, на источник и **снять остаток резерва**; строки коробов обнулить.
- Файлы: `marketplace_unload_service.py` (cancel path), `marketplace_unload_collect_service.py`, `inventory_service.py`.
- Готово: после cancel остаток восстановлен 1-в-1, висящих резервов нет. **Тест:** отмена частично распределённой отгрузки.
- Зависит: TASK-004.

### TASK-020 (НОВАЯ). Селлер — plan-only паритет (DEC-015)
- **Статус:** READY. **Тип:** UI. **Треб.:** DEC-015, BR-015.
- Цель: `SellerMarketplaceUnloadDialog` — только вкладка плана + статусы; без коробов/ячеек/завершения упаковки/ШК.
- Готово: селлер не видит и не вызывает короба/ячейки/complete. **Тест:** e2e на ограниченный набор действий селлера.
- Зависит: TASK-012.

### Обновлённый Implementation Order (вставки)
- **TASK-004** — на этом же шаге добавить леджер + локи (DEC-016/017).
- После **TASK-004** → **TASK-019** (откат при отмене).
- **TASK-007** — включить ЧЗ-gate (DEC-014) и reopen-on-plan-edit (DEC-013).
- **TASK-014/015** — путь недопоставки (DEC-012).
- После **TASK-012** → **TASK-020** (селлер plan-only).
