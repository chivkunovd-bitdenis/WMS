# Аудит сквозного флага адресного хранения

Дата: 2026-08-28.

Источник правила: `Tenant.address_storage_enabled`, чтение только через
`tenant_settings_service.is_address_storage_enabled`.

Продуктовое правило: когда адресное хранение выключено, оператор не выбирает и
не видит ячейку. Остаток учитывается на товаре или таре, а обязательная для
внутреннего складского журнала ссылка ведёт в служебную зону `__SORTING__`,
созданную через `sorting_location_service.get_or_create_sorting_location`.
Служебная зона не является пользовательской ячейкой и наружу не показывается.

## Backend: место — что было — что стало

| Место | Что было | Что стало при выключенном адресном хранении |
|---|---|---|
| `services/marketplace_unload_collect_service.py`, `marketplace_unload_box_service.py`, `marketplace_unload_pick_service.py` | Основной сбор в короб уже умел обходиться без выбранной ячейки, но legacy-скан подбора всё ещё отвечал `location_required`, а созданная внутренняя аллокация возвращала фактический адрес. | Сервис сам выбирает доступный внутренний остаток/служебную зону. И коробочный, и legacy-скан принимают товар сразу, не распознают скан как пользовательскую ячейку и не требуют `storage_location_id`. `api/marketplace_unload_requests.py` скрывает адрес в скане, деталях и аллокациях, а `pick-options` возвращает товар без списка ячеек. |
| `services/inbound_intake_service.py` — создание строки | Передать ячейку было необязательно, но дальнейшее оприходование хорошего товара без неё завершалось `lines_missing_storage`. Переданная клиентом ячейка сохранялась даже для арендатора без адресного хранения. | Переданный адрес игнорируется. Строка остаётся без пользовательской ячейки. |
| `services/inbound_intake_service.py` — `receive_line` и `post_all_remaining` | После приёмки товар попадал в `__SORTING__`, но завершение требовало переноса в обычную ячейку. | Хороший товар остаётся во внутренней зоне `__SORTING__`, строка считается оприходованной и приёмка завершается. Брак по-прежнему переносится в отдельную служебную зону брака. Для арендатора с включённым флагом старый перенос в выбранную ячейку не менялся. |
| `services/inbound_intake_service.py` — назначение ячейки | PATCH сохранял выбранную ячейку. | При выключенном флаге PATCH не может вернуть адрес в процесс: значение очищается. |
| `api/inbound_intake.py` | Строки, движения и черновики распределения возвращали `storage_location_id/code`; распределительный ответ возвращал активную ячейку. | В пользовательских ответах эти поля `null`. Внутренняя ссылка движения сохраняется в БД. Обычный сценарий без адресов завершается через «оприходовать всё», поэтому распределение по ячейкам не нужно. |
| `services/outbound_shipment_service.py` | Строку можно было создать без ячейки, но `ship/post` падал с `storage_not_assigned` / `lines_missing_storage`. | При создании, submit, частичной и полной отгрузке строка автоматически привязывается к `__SORTING__`. Пользователь ничего не выбирает. Для включённого флага валидация и списание из выбранной ячейки прежние. |
| `api/outbound_shipment.py` | Ответы строки и движений показывали внутренний адрес. | `storage_location_id/code` возвращаются как `null`; движение остаётся восстановимым по БД. |
| `services/packaging_task_service.py`, `api/packaging_tasks.py` | Пустая ячейка уже заменялась на `__SORTING__`, но явно переданный адрес принимался, а строки и события всегда показывали ячейку. | При выключенном флаге любой входной адрес заменяется на `__SORTING__`; строки и события упаковки возвращают адрес как `null`. Для включённого флага всё осталось как было. |
| `services/fbs_supply_service.py`, `fbs_workspace_service.py` | Сборка FBS уже автоматически проходила этап подбора без адресного хранения, но workspace мог подмешать `__SORTING__` как будто это обычная ячейка. | Автопрохождение сохранено, fallback-ячейка больше не добавляется. Причина автопрохождения остаётся видимой оператору. |
| `services/fbs_worklist_service.py` | Worklist возвращал `inventory.locations` и `pick.location_code`, включая служебную зону после автоподбора. | Список мест пуст, код места подбора `null`, общий доступный остаток товара остаётся в ответе. Ячеечные команды `fbs_picking_service.py` остаются только для режима с включённым адресным хранением; при выключенном режиме нормальный workflow до них не доходит, потому что `fbs_supply_service` автоматически закрывает подбор. |
| `api/warehouses.py`, `services/catalog_service.py` | API перечислял, создавал, переименовывал, удалял и разрешал по штрихкоду обычные и служебные ячейки независимо от флага. | Список ячеек пуст. Получение служебной зоны, создание/редактирование/удаление, стеллажи, подсказка следующего адреса и разрешение штрихкода ячейки блокируются `address_storage_disabled`. Внутренние функции каталога не менялись: они нужны журналу и арендаторам с включённым флагом. |
| `api/inventory_balances.py`, `services/inventory_service.py` | Подсказки по местам возвращали ячейки; просмотр остатка требовал `storage_location_id`; сводка считала весь остаток в `__SORTING__` недоступным. | `locations-by-product` возвращает пустой список. Ячеечный просмотр остатка блокируется `address_storage_disabled`, вместо того чтобы заставлять интерфейс знать UUID служебной зоны. В сводке служебная зона схлопывается в обычный остаток товара: `quantity_in_sorting=0`, `quantity_in_storage=quantity`, доступность считается без вычитания скрытой зоны. Внутренний ledger по-прежнему требует location FK и пишет его в `__SORTING__`. |
| `api/inventory_movements.py` и movement-ответы приёмки/отгрузки | API возвращал внутренний `storage_location_id`. | Поле `null` при выключенном флаге. Суммы, тип движения, товар и время не скрываются. `inventory_movement_report_service.py` использует location только для фильтра по складу и не показывает ячейку, поэтому его менять не требовалось. |
| `api/stock_transfer.py` | Запрос всегда требовал ячейку «откуда» и «куда». | Операция блокируется `address_storage_disabled`: перемещение между ячейками не существует в безадресном режиме. Включённый режим не изменён. |
| `services/marking_code_service.py`, `api/marking_codes.py` | Очередь маркировки связывала строку упаковки с `StorageLocation` и всегда возвращала код. | Внутренняя связь и сортировка очереди сохранены, но `storage_location_code` в API становится `null`. |
| `services/fbs_packaging_stock_service.py`, `fbs_packaging_integration_service.py`, `fbs_ozon_packaging_service.py` | Для атомарного списания и возврата использовалась location FK. | Изменение не нужно: это внутренние движения; без адресного хранения источник уже `__SORTING__` благодаря автопрохождению FBS и упаковочному fallback. Пользовательский workspace адрес не показывает. |
| `services/defect_warehouse_service.py`, `discrepancy_act_service.py`, `box_import_service.py`, `warehouse_box_service.py` | Используют служебные зоны либо nullable location как техническую часть учёта. | Изменение не нужно. Зона брака и `__SORTING__` остаются внутренними местами журнала; API не предлагает их как пользовательскую ячейку. |
| `services/reporting_service.py`, `inventory_movement_report_service.py`, `stock_direction_service.py`, `fbs_stock_availability_service.py` | Join со `StorageLocation` нужен для определения склада и агрегации остатка. | Изменение не нужно: эти сервисы не требуют выбора ячейки и не возвращают её пользователю. Исключать `__SORTING__` нельзя — это единственный физический остаток безадресного арендатора. |

Миграция БД не потребовалась: обязательные внешние ключи остаются заполненными
служебной зоной, а скрытие адреса выполнено на границе пользовательского API.

## Проверки

- `test_address_storage_cross_system.py`: приёмка → упаковка → исходящая
  отгрузка без ячейки; адрес отсутствует в строках и движениях; ячеечные API
  недоступны.
- `test_marketplace_unload_address_storage.py`: сбор в короб без адреса,
  скрытые аллокации и пустые location-options.
- `test_fbs_worklist_query_count.py`: FBS worklist не возвращает места.
- `test_marking_pending.py`: очередь маркировки не показывает место.
- `test_tenant_settings.py`: остаток действительно мигрирует в `__SORTING__`,
  но служебная зона не раскрывается через каталог ячеек.

## ЧТО ОСТАЛОСЬ ВО ФРОНТЕ

Ниже перечислены файлы, которые сами не читают
`address_storage_enabled`/`addressStorageEnabled` и при этом рисуют ячейку,
предлагают выбрать её или ведут на ячеечный экран. Backend теперь не отдаёт им
служебный адрес, но владелец фронта должен скрыть сами подписи, колонки, поля и
маршруты.

### Живые экраны и навигация

- `frontend/src/layouts/AuthedAppLayout.tsx` — пункт «Ячейки».
- `frontend/src/sections/CatalogSection.tsx` — полный CRUD, печать и список
  ячеек.
- `frontend/src/sections/OperationsSection.tsx` — ячейки при приёмке,
  отгрузке и отдельное перемещение между ячейками.
- `frontend/src/screens/v2/InboundScreen.tsx` — показ и назначение ячейки в
  приёмке.
- `frontend/src/screens/v2/OutboundScreen.tsx` — показ и назначение ячейки
  отбора.
- `frontend/src/screens/v2/TransfersScreen.tsx` — экран целиком требует две
  ячейки.
- `frontend/src/screens/ff/FfInboundQueuePage.tsx` — тексты и пустые состояния
  про раскладку по ячейкам.
- `frontend/src/screens/ff/FfInboundSortingPanel.tsx` — весь сценарий скана и
  распределения по ячейкам.
- `frontend/src/screens/ff/FfPackagingPage.tsx` — фильтр, колонка, подписи и
  создание задания из ячейки.
- `frontend/src/screens/ff/FfPendingMarkingPage.tsx` — колонка «Ячейка».
- `frontend/src/screens/ff/FfMpUnloadPickPanel.tsx` — скан, активная ячейка и
  строки мест подбора.
- `frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx` — подтверждение, ручной
  выбор и возврат в ячейку.
- `frontend/src/screens/v2/fbsUx.ts` — печатная форма FBS с колонкой ячейки.
- `frontend/src/screens/v2/FfProductsCatalogScreen.tsx` — показатель «В
  ячейках».
- `frontend/src/screens/v2/SellerProductsStockScreen.tsx` — показатель «В
  ячейках».

Уже учитывают флаг и потому в список долга не входят:
`App.tsx`, `FfInboundRequestView.tsx`, `FfSuppliesShipmentsPage.tsx`,
`FfMarketplaceUnloadBoxAddDialog.tsx`, `FfSettingsScreen.tsx`.

### Макеты и новые складские экраны, которые тоже нельзя выпускать без gate по флагу

- `frontend/src/screens/ff/warehouse-map/FfWarehouseMapScreen.tsx`
- `frontend/src/screens/ff/warehouse-map/WarehouseMapToolbar.tsx`
- `frontend/src/screens/ff/warehouse-map/WarehouseMapTree.tsx`
- `frontend/src/screens/ff/warehouse-map/WarehouseMapMoveDialog.tsx`
- `frontend/src/screens/ff/warehouse-map/WarehouseMapJournal.tsx`
- `frontend/src/screens/ff/warehouse-map/WarehouseMapRows.ts`
- `frontend/src/screens/ff/warehouse-map/preview.tsx`
- `frontend/src/screens/ff/warehouse-map/stub.ts`
- `frontend/src/screens/ff/warehouse-map/lab/MoveLab.tsx`
- `frontend/src/screens/ff/warehouse-map/lab/MoveLabPlan.tsx`
- `frontend/src/screens/ff/warehouse-map/lab/labData.ts`
- `frontend/src/screens/ff/sorting-objects/SortingObjectsScreen.tsx`
- `frontend/src/screens/ff/sorting-objects/ObjectsTree.tsx`
- `frontend/src/screens/ff/sorting-objects/objectsRows.ts`
- `frontend/src/screens/ff/sorting-objects/objectsStub.ts`
- `frontend/src/screens/ff/unload-pick/UnloadPickScreen.tsx`
- `frontend/src/screens/ff/unload-pick/PickPlacesTree.tsx`
- `frontend/src/screens/ff/unload-pick/pickRows.ts`
- `frontend/src/screens/ff/unload-pick/pickStub.ts`
- `frontend/src/screens/ff/unload-pick-2/UnloadPickRouteScreen.tsx`
- `frontend/src/screens/ff/unload-pick-2/PlaceCard.tsx`
- `frontend/src/screens/ff/unload-pick-2/routeRows.ts`
- `frontend/src/screens/ff/inventory/FfInventoryCountScreen.tsx`
- `frontend/src/screens/ff/inventory/InventoryTree.tsx`
- `frontend/src/screens/ff/inventory/InventoryRows.ts`
- `frontend/src/screens/ff/inventory/stub.ts`

Типы и API-обёртки (`fbsApi.ts`, `pendingMarkingApi.ts`, `InventoryTypes.ts`,
`WarehouseMapTypes.ts`) сами ничего не показывают; менять их надо только вместе
с соответствующим экраном, если nullable-поля backend потребуют уточнить в
TypeScript.
