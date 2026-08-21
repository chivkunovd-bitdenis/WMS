# BLG-I10 - MODULE-DOSSIER: склад и ячейка

## 1. Паспорт исследования

- Task: `BLG-I10`
- Stage: `S03 DOMAIN_RESEARCH`
- Role: `pipeline-ba`
- Trait: `new_module`
- Risk: `high`
- Baseline SHA: `69c271678782d7dcfa39df97cd905cbee1678727`
- Исследовано: `2026-08-21`
- Scope: выбор физического склада фулфилмента, модель ячейки, остаток и резерв в разрезе
  склада/ячейки, FBS-привязки, приёмка, сортировка, подбор, упаковка, короба, отгрузка и возврат
  остатка.
- Предлагаемый verdict S03: `RESEARCH_READY`.
- Blocking research questions: `0`.
- Необработанные применимые строки capability matrix: `0`.

## 2. Короткий вывод

Инцидент BLG-I10 вызван не отсутствием ещё одного селектора, а смешением двух разных сущностей.
Физический склад фулфилмента отвечает на вопрос «где реально лежит товар», а склад продавца WB
отвечает на вопрос «через какой внешний узел публикуется остаток и приходят FBS-заказы». В текущей
модели оба понятия сведены к `warehouses.id`: если для WB-привязки нет явного соответствия, сервис
создаёт обычный WMS-склад `FBS WB <id>`. Для каждого такого склада затем появляется собственная
`__SORTING__`, поэтому один физический остаток искусственно дробится.

Целевая capability должна сохранить строгий складской учёт, но убрать технический выбор из
односкладского сценария:

1. `Warehouse` остаётся физическим контуром остатков и операций.
2. `StorageLocation` остаётся местом внутри одного физического склада; `__SORTING__` является
   виртуальным операционным местом этого склада, а не заменой склада.
3. Внешний `warehouseId` WB хранится как отдельная интеграционная идентичность и связывается с
   физическим WMS-складом явно; автоматическое создание видимого физического склада из внешнего ID
   не должно быть неявным fallback.
4. При одном физическом складе UI и API-клиенты получают его как однозначный default и не требуют
   выбора. При двух и более физически доступных складах выбор появляется в рабочем контексте;
   выбранная ячейка обязана принадлежать выбранному складу.
5. Документ нельзя создать/продолжить как будто товар есть, если доступный остаток находится только
   на другом складе. Ошибка должна назвать текущий склад и склад, где остаток найден, до начала
   длительной упаковки.
6. Ячейка помогает найти и подобрать товар. Обязательность ячейки для фактической проводки зависит
   от режима адресного хранения и должна быть утверждена Product на S07, потому что источник BLG-I10
   конфликтует с действующим `DEC-019`/`lines_missing_storage`.
7. Короб является контейнером товара. Его текущая ячейка может быть полезной координатой, но не
   должна становиться самостоятельным бизнес-условием отгрузки, если состав, склад и фактическое
   сканирование уже доказаны.

## 3. Термины и граница WMS

| Термин | Рабочее определение для следующих стадий | Не смешивать с |
|---|---|---|
| Физический склад ФФ | Реальная площадка, в пределах которой учитывается on-hand, резерв и движение | складом WB, ПВЗ, сортировочным центром WB |
| Ячейка (`StorageLocation`) | Адрес или операционная зона внутри одного физического склада | складом, коробом, внешним `warehouseId` |
| `__SORTING__` | Виртуальное операционное место внутри конкретного склада для принятого, но не разложенного товара | общим межскладским остатком |
| Склад продавца WB | Внешний узел WB для FBS-заказов и публикации остатка; имеет WB `warehouseId` | физическим WMS-складом без явной mapping policy |
| Склад WB / офис WB | Внешнее место сдачи, к которому WB привязывает склад продавца | местом хранения товара у фулфилмента |
| Короб | Физический контейнер с собственным штрихкодом и составом | ячейкой; короб может находиться в ячейке, но не является ячейкой |
| Доступный остаток | On-hand физического склада минус активные резервы и иные непригодные количества | суммой всех складов без явного выбора |

**Граница ответственности WMS.** WMS хранит физическое место, остаток, резерв, перемещение,
операторский контекст и доказательство сканирования. WB задаёт внешний `warehouseId`, правила
группировки FBS-заказов и API публикации остатков. WMS не должна выводить физическое наличие из
внешнего ID автоматически; она обязана хранить явную связь внешнего узла с физическим складом.

## 4. Источники

### 4.1. Внутренние источники на baseline

| ID | Источник | Что подтверждает | Уровень |
|---|---|---|---|
| SRC-I01 | `docs/BACKLOG-2026-08-19-CHAT-RU.md:661-711`, версия на baseline, проверено 2026-08-21 | Инцидент 155/189 заказов, 519 единиц/37 SKU, один физический склад, требование one-warehouse/no-choice и multiwarehouse switch | `observed` |
| SRC-I02 | `backend/app/models/warehouse.py:20-35` | `Warehouse` имеет tenant/name/code, но не имеет типа, физического адреса, default-флага или штрихкода | `observed` |
| SRC-I03 | `backend/app/models/storage_location.py:22-51` | Ячейка принадлежит одному складу; code уникален в складе, barcode уникален в tenant | `observed` |
| SRC-I04 | `backend/app/services/wb_marketplace_orders_service.py:274-308` | При отсутствии binding создаётся обычный WMS-склад `FBS WB <id>` | `observed` |
| SRC-I05 | `backend/app/models/fbs_warehouse_binding.py:28-65` | Внешний WB-склад связан с WMS-складом; уникальность запрещает два WB warehouse одного seller на один WMS warehouse | `observed` |
| SRC-I06 | `backend/app/models/fbs_order.py:177-202,359-388` | FBS-заказ и резерв закрепляются за WMS warehouse, отдельно хранится `wb_warehouse_id` | `observed` |
| SRC-I07 | `backend/app/models/fbs_supply.py:33-63` и `backend/app/services/fbs_supply_validator_service.py:169-200` | FBS-поставка имеет один WMS warehouse; смешение WB/WMS warehouses запрещается | `observed` |
| SRC-I08 | `backend/app/services/fbs_supply_validator_service.py:130-153,215-275` | Preflight считает доступность по WMS warehouse и выдаёт per-order issue, но не сообщает склад, где товар фактически найден | `observed` |
| SRC-I09 | `backend/app/services/fbs_picking_service.py:50-100,169-180,247-317` | Подбор принимает только ячейку склада поставки и переносит товар в `__SORTING__` того же склада | `observed` |
| SRC-I10 | `backend/app/models/inventory_reservation.py:19-58` и `backend/app/services/inventory_service.py:428-495` | Outbound уже умеет резервировать по ячейке или по складу, когда ячейка ещё не выбрана | `observed` |
| SRC-I11 | `backend/app/services/outbound_shipment_service.py:140-235,275-300,357-386` | Ячейка опциональна до submit, но фактический ship/post блокируется без неё | `observed` |
| SRC-I12 | `backend/app/models/warehouse_box.py:18-46` | Короб привязан к складу, а ячейка у него nullable | `observed` |
| SRC-I13 | `frontend/src/App.tsx:1069-1102,1608-1638` | UI уже автоподставляет единственный склад, но считает все записи `warehouses`, включая auto-FBS | `observed` |
| SRC-I14 | `docs/MVP_DECISIONS_RU.md:97-112` | Действующий oracle: `__SORTING__`, address-storage toggle, warehouse-level reserve без ячейки, ячейка обязательна для фактического подбора | `official` |
| SRC-I15 | `backend/app/api/warehouses.py:72-215` | Все tenant users читают склады/ячейки; склад создаёт FF admin; отдельной warehouse assignment модели нет | `observed` |
| SRC-I16 | `frontend/screens.registry.json:88-175,1079-1135,1607-1905` | Затронутые поверхности: S-03 FBS, S-14 упаковка, S-20 сортировка, S-22 приёмка, S-24 отгрузка | `observed` |

### 4.2. Официальные внешние источники и competitor workflow

| ID | Источник, версия и дата | Проверяемый claim | Уровень |
|---|---|---|---|
| SRC-E01 | [WB API: склады продавца и остатки](https://dev.wildberries.ru/docs/openapi/work-with-products), live OpenAPI без номера версии, доступ 2026-08-21 | WB ведёт seller warehouses отдельными `warehouseId`; остаток публикуется в `/api/v3/stocks/{warehouseId}`; seller warehouse связывается с офисом WB | `official` |
| SRC-E02 | [WB API: заказы FBS](https://dev.wildberries.ru/knowledge-base/articles/019d49a4-0771-7571-aea9-11d5b597f34c/zakazy-fbs), опубликовано 2026-04, доступ 2026-08-21 | В одну FBS-поставку входят задания одного `warehouseId`; это внешний инвариант группировки, а не доказательство физического WMS-остатка | `official` |
| SRC-E03 | [Odoo 18: Inventory management](https://www.odoo.com/documentation/18.0/applications/inventory_and_mrp/inventory/warehouses_storage/inventory_management.html), версия 18.0, доступ 2026-08-21 | Warehouse представляет физическое место; locations являются подразделениями внутри конкретного warehouse | `official` |
| SRC-E04 | [Odoo 18: Locations](https://www.odoo.com/documentation/18.0/applications/inventory_and_mrp/inventory/warehouses_storage/inventory_management/use_locations.html), версия 18.0, доступ 2026-08-21 | Storage locations включаются как capability, имеют иерархию и barcode; current stock доступен по location | `official` |
| SRC-E05 | [Odoo 18: Barcode receipts/deliveries](https://www.odoo.com/documentation/18.0/applications/inventory_and_mrp/barcode/operations/receipts_deliveries.html), версия 18.0, доступ 2026-08-21 | В рабочем экране источник подбора виден и может быть сменён, если товар лежит в нескольких locations; scanner управляет процессом без ухода в настройки | `official` |
| SRC-E06 | [Microsoft Business Central: locations with bins](https://learn.microsoft.com/en-ca/dynamics365/business-central/warehouse-how-to-set-up-locations-to-use-bins), обновлено 2026-05-18, доступ 2026-08-21 | Bin mandatory включается на уровне warehouse location; default bins подставляются в receipts/shipments, а не требуют ручного выбора каждый раз | `official` |
| SRC-E07 | [Microsoft Business Central: warehouse picking](https://learn.microsoft.com/en-us/dynamics365/business-central/warehouse-how-to-pick-items-for-warehouse-shipment), обновлено 2024-04-23, доступ 2026-08-21 | Pickable quantity учитывает locations, reservations и blocked bins; система предлагает bins и поддерживает подбор одной строки из нескольких bins | `official` |
| SRC-E08 | [Odoo 18: multi-package shipments](https://www.odoo.com/documentation/18.0/applications/inventory_and_mrp/inventory/shipping_receiving/setup_configuration/multipack.html), версия 18.0, доступ 2026-08-21 | Package является контейнером состава в shipment workflow; подтверждение shipment основано на составе/количестве, а не на превращении package в storage location | `official` |

Скриншоты в официальных competitor-документах используются только как workflow reference:
Odoo показывает форму location, current-stock view и scanner delivery; Microsoft показывает Location
Card с `Bin Mandatory` и pick lines `Take/Place`. В S03 макеты WMS не создаются.

## 5. Подтверждённая модель AS-IS

### 5.1. Сущности и связи

```text
Tenant
  +-- Warehouse (без type/default/barcode)
        +-- StorageLocation (включая отдельную __SORTING__)
        |     +-- InventoryBalance(product, quantities)
        +-- InboundIntakeRequest
        +-- OutboundShipmentRequest
        +-- FbsSupply
        +-- WarehouseBox (storage_location_id nullable)

Seller + WB warehouseId
  +-- FbsWarehouseBinding --> Warehouse
  +-- FbsOrder.warehouse_id --> Warehouse
  +-- FbsOrderReservation.warehouse_id --> Warehouse
```

### 5.2. Что уже работает и должно быть переиспользовано

- Tenant isolation присутствует во всех основных warehouse/location запросах.
- Ячейка строго принадлежит одному складу.
- Остаток хранится по ячейке, а суммарный остаток вычисляется по складу.
- Резерв outbound уже поддерживает две фазы: warehouse-level до назначения ячейки и
  location-level после назначения.
- `__SORTING__` обеспечивает работу без полной адресной раскладки, но сейчас создаётся отдельно на
  каждый WMS warehouse.
- Inbound/outbound UI уже умеет автоматически выбрать склад, если в общем списке ровно одна запись.
- FBS preflight уже запускается до создания поставки и возвращает issues по заказам.
- FBS picking валидирует, что ячейка принадлежит складу поставки.
- Короб уже технически допускает отсутствие `storage_location_id`.

### 5.3. Где модель расходится с бизнес-смыслом BLG-I10

1. У `Warehouse` нет классификации `physical | integration_projection`, поэтому auto-FBS warehouse
   попадает в обычный список и увеличивает число «складов» для UI.
2. Auto-binding создаёт новый WMS warehouse из внешнего WB `warehouseId`; вместе с ним появляется
   отдельная `__SORTING__`, хотя физически товар может лежать на единственной площадке.
3. FBS order/supply/reservation наследуют auto-created warehouse и затем корректно, но по неверной
   физической границе, ищут остаток только там.
4. Существующий preflight умеет сказать «недостаточно остатка», но не делает cross-warehouse lookup,
   поэтому не говорит «519 шт. находятся на складе Основной».
5. У склада нет barcode, значит требование «скан склада переключает склад» не поддерживается моделью.
   Barcode ячейки уже однозначно ведёт к warehouse и может безопасно переключать пару
   `warehouse + location`, если это утвердит процесс.
6. Barcode namespaces для warehouse/location/box/product не объединены. Для универсального scanner
   resolver потребуется typed prefix или правило разрешения коллизий.
7. Режим `address_storage_enabled=false` уже означает работу через `__SORTING__`, но текущий oracle
   всё равно требует location для фактического generic outbound. Это противоречит формулировке
   BLG-I10 «ячейка не должна блокировать фактическую отгрузку без отдельной бизнес-причины».
8. `WarehouseBox.storage_location_id` nullable, однако downstream workflows могут проверять warehouse
   коробов. Нужно сохранить warehouse integrity, не превращая nullable cell в обязательный shipment
   gate.
9. Нет per-warehouse assignment для операторов: любой аутентифицированный пользователь tenant видит
   все склады. Для нескольких физических площадок это риск ошибочного выбора и будущий access gap.

## 6. Competitor workflow: что брать, а что не копировать

### Odoo 18

Сильное решение: физический warehouse отделён от locations; locations можно включить как более
детальный режим, а barcode location используется прямо в scanner workflow. В delivery screen source
location виден и меняется, если запас распределён по нескольким местам. Также у новой базы есть
преднастроенный warehouse, то есть простой сценарий стартует без ручного проектирования структуры.

Ограничение для WMS: Odoo допускает глубокую иерархию locations и множество route-настроек. Для
BLG-I10 достаточно двух уровней `physical warehouse -> storage/operational location`; перенос всей
иерархии создаст лишнюю сложность.

### Microsoft Business Central

Сильное решение: обязательность bin включается на уровне location/warehouse configuration, default
bin подставляется автоматически, а pickable quantity отдельно объясняет, сколько товара физически
есть и сколько реально доступно для подбора. Pick может состоять из нескольких bin lines.

Ограничение для WMS: Business Central предлагает четыре уровня сложности warehouse processing. Для
BLG-I10 это reference для progressive disclosure, но не основание вводить отдельные документы
`Take/Place` или полный directed put-away.

### Вывод для следующих стадий

Нужна progressive disclosure: один physical warehouse является системным контекстом без видимого
выбора; второй physical warehouse включает явный выбор и stock guard. Ячейки могут быть строгими при
адресном хранении и виртуальными/default при простом режиме. Внешние marketplace warehouses остаются
в integration mapping и не увеличивают число физических складов в операторском UI.

## 7. Машинная capability matrix

Статус `covered` означает, что capability уже подтверждена и переиспользуется; `gap` означает
конкретный разрыв; `decision_required` означает, что исследование закончено, но продуктовый oracle
принимается на S07; `not_applicable` означает проверенную неприменимость. Все применимые строки
обработаны и имеют downstream owner.

```json
{
  "schema": "wms.module-capability-matrix.v1",
  "task_id": "BLG-I10",
  "module": "warehouse_location_context",
  "generated_at": "2026-08-21",
  "baseline_sha": "69c271678782d7dcfa39df97cd905cbee1678727",
  "rows": [
    {
      "id": "CAP-01",
      "lane": "bootstrap",
      "capability": "Default physical warehouse and sorting location exist for a new tenant",
      "applicable": true,
      "status": "gap",
      "source_ids": ["SRC-I01", "SRC-I02", "SRC-E03"],
      "downstream_owner": "S05"
    },
    {
      "id": "CAP-02",
      "lane": "catalog",
      "capability": "Physical WMS warehouse is typed separately from WB integration warehouse identity",
      "applicable": true,
      "status": "gap",
      "source_ids": ["SRC-I02", "SRC-I04", "SRC-I05", "SRC-E01", "SRC-E03"],
      "downstream_owner": "S07/S13"
    },
    {
      "id": "CAP-03",
      "lane": "locations",
      "capability": "Every storage or operational location belongs to exactly one physical warehouse",
      "applicable": true,
      "status": "covered",
      "source_ids": ["SRC-I03", "SRC-E03"],
      "downstream_owner": "S05"
    },
    {
      "id": "CAP-04",
      "lane": "single_warehouse_ux",
      "capability": "One physical warehouse is auto-selected and warehouse controls are hidden",
      "applicable": true,
      "status": "gap",
      "source_ids": ["SRC-I01", "SRC-I04", "SRC-I13"],
      "downstream_owner": "S05/S07"
    },
    {
      "id": "CAP-05",
      "lane": "multi_warehouse_ux",
      "capability": "Two or more accessible physical warehouses expose an in-workspace selector before location",
      "applicable": true,
      "status": "decision_required",
      "source_ids": ["SRC-I01", "SRC-E05"],
      "downstream_owner": "S05/S07"
    },
    {
      "id": "CAP-06",
      "lane": "scanner",
      "capability": "Warehouse barcode switches warehouse and location barcode selects its owning warehouse/location",
      "applicable": true,
      "status": "gap",
      "source_ids": ["SRC-I01", "SRC-I02", "SRC-I03", "SRC-E04", "SRC-E05"],
      "downstream_owner": "S05/S13"
    },
    {
      "id": "CAP-07",
      "lane": "scanner",
      "capability": "Barcode kind collision is resolved deterministically across warehouse, location, box and product",
      "applicable": true,
      "status": "decision_required",
      "source_ids": ["SRC-I03", "SRC-I12"],
      "downstream_owner": "S13"
    },
    {
      "id": "CAP-08",
      "lane": "inbound",
      "capability": "Inbound is posted to one physical warehouse and accepted stock lands in its sorting/default location",
      "applicable": true,
      "status": "covered",
      "source_ids": ["SRC-I03", "SRC-I13", "SRC-I14"],
      "downstream_owner": "S05"
    },
    {
      "id": "CAP-09",
      "lane": "sorting",
      "capability": "Putaway chooses only locations inside the current warehouse and reports stock by location",
      "applicable": true,
      "status": "covered",
      "source_ids": ["SRC-I03", "SRC-I14", "SRC-E04"],
      "downstream_owner": "S05"
    },
    {
      "id": "CAP-10",
      "lane": "inventory",
      "capability": "On-hand and available quantities are queryable by physical warehouse and by location",
      "applicable": true,
      "status": "covered",
      "source_ids": ["SRC-I03", "SRC-I10", "SRC-E07"],
      "downstream_owner": "S06"
    },
    {
      "id": "CAP-11",
      "lane": "reservation",
      "capability": "Demand reserves at warehouse level before source location is known and narrows to location at pick",
      "applicable": true,
      "status": "covered",
      "source_ids": ["SRC-I10", "SRC-I14", "SRC-E07"],
      "downstream_owner": "S05"
    },
    {
      "id": "CAP-12",
      "lane": "stock_guard",
      "capability": "Creation/preflight blocks a document whose selected warehouse lacks stock and names another warehouse that has it",
      "applicable": true,
      "status": "gap",
      "source_ids": ["SRC-I01", "SRC-I08", "SRC-E07"],
      "downstream_owner": "S05/S07"
    },
    {
      "id": "CAP-13",
      "lane": "fbs_external_contract",
      "capability": "WB warehouseId remains the external stock/order grouping key without becoming physical stock evidence",
      "applicable": true,
      "status": "gap",
      "source_ids": ["SRC-I04", "SRC-I05", "SRC-E01", "SRC-E02"],
      "downstream_owner": "S07/S13"
    },
    {
      "id": "CAP-14",
      "lane": "fbs_supply",
      "capability": "Supply composition obeys one WB warehouseId and one resolved physical WMS warehouse",
      "applicable": true,
      "status": "covered",
      "source_ids": ["SRC-I06", "SRC-I07", "SRC-E02"],
      "downstream_owner": "S05"
    },
    {
      "id": "CAP-15",
      "lane": "picking",
      "capability": "Pick source belongs to supply warehouse; stock may be split across several cells",
      "applicable": true,
      "status": "gap",
      "source_ids": ["SRC-I09", "SRC-E07"],
      "downstream_owner": "S05/S07"
    },
    {
      "id": "CAP-16",
      "lane": "address_storage",
      "capability": "Address-storage off uses a default operational location and does not ask the operator for a cell",
      "applicable": true,
      "status": "decision_required",
      "source_ids": ["SRC-I01", "SRC-I11", "SRC-I14", "SRC-E06"],
      "downstream_owner": "S07"
    },
    {
      "id": "CAP-17",
      "lane": "boxes",
      "capability": "Box belongs to the operation/warehouse; current location is nullable and is not an independent shipment gate",
      "applicable": true,
      "status": "decision_required",
      "source_ids": ["SRC-I01", "SRC-I12", "SRC-E08"],
      "downstream_owner": "S07"
    },
    {
      "id": "CAP-18",
      "lane": "packing_marking_print",
      "capability": "Packing, marking and print consume the resolved warehouse context but do not define a new warehouse identity",
      "applicable": true,
      "status": "covered",
      "source_ids": ["SRC-I07", "SRC-I09", "SRC-I16"],
      "downstream_owner": "S05"
    },
    {
      "id": "CAP-19",
      "lane": "shipment",
      "capability": "Actual shipment proves stock deduction from the resolved warehouse; exact cell requirement follows approved address-storage policy",
      "applicable": true,
      "status": "decision_required",
      "source_ids": ["SRC-I10", "SRC-I11", "SRC-I14", "SRC-E06"],
      "downstream_owner": "S07"
    },
    {
      "id": "CAP-20",
      "lane": "cancel_return",
      "capability": "Cancellation or undo restores stock to the same physical warehouse with an explicit source/default-location rule",
      "applicable": true,
      "status": "decision_required",
      "source_ids": ["SRC-I09", "SRC-I14"],
      "downstream_owner": "S05/S07"
    },
    {
      "id": "CAP-21",
      "lane": "roles_tenant_security",
      "capability": "Tenant isolation is preserved and multiwarehouse operators see only authorized warehouses",
      "applicable": true,
      "status": "gap",
      "source_ids": ["SRC-I03", "SRC-I15"],
      "downstream_owner": "S07/S13"
    },
    {
      "id": "CAP-22",
      "lane": "batch_partial_success",
      "capability": "Bulk FBS preflight handles at least 155/189 orders atomically and returns per-order warehouse issues",
      "applicable": true,
      "status": "gap",
      "source_ids": ["SRC-I01", "SRC-I08"],
      "downstream_owner": "S15"
    },
    {
      "id": "CAP-23",
      "lane": "degraded_emergency",
      "capability": "No-stock-on-selected-warehouse is a visible business stop; no automatic cross-warehouse move or silent fallback occurs",
      "applicable": true,
      "status": "decision_required",
      "source_ids": ["SRC-I01", "SRC-I08"],
      "downstream_owner": "S07/S13"
    },
    {
      "id": "CAP-24",
      "lane": "pagination_rate_limit_webhook_retry",
      "capability": "No new external endpoint, pagination, webhook or retry contract is introduced by BLG-I10",
      "applicable": false,
      "status": "not_applicable",
      "source_ids": ["SRC-E01", "SRC-E02"],
      "downstream_owner": "S04"
    },
    {
      "id": "CAP-25",
      "lane": "mobile_contract",
      "capability": "Existing mobile/TSD consumers must receive warehouse plus location without a breaking response change",
      "applicable": true,
      "status": "decision_required",
      "source_ids": ["SRC-I03", "SRC-I09"],
      "downstream_owner": "S13/S15"
    }
  ],
  "summary": {
    "applicable_rows": 24,
    "covered": 7,
    "gaps": 9,
    "decision_required": 8,
    "not_applicable": 1,
    "unhandled_applicable_rows": 0
  }
}
```

## 8. Применимые состояния и инварианты

### Состояние складского контекста

```text
NO_PHYSICAL_WAREHOUSE
  -> bootstrap creates DEFAULT_PHYSICAL_WAREHOUSE + DEFAULT_SORTING_LOCATION

ONE_PHYSICAL_WAREHOUSE
  -> warehouse context implicit
  -> location implicit when address storage is off
  -> location scanned/selected when address storage is on

MULTIPLE_PHYSICAL_WAREHOUSES
  -> warehouse context must be resolved before stock commitment
  -> location may only be resolved inside that warehouse
  -> changing warehouse after reservation/pick requires explicit replan, never silent mutation
```

Обязательные инварианты для S05-S15:

- `location.warehouse_id == operation.warehouse_id` для каждой адресной операции.
- Внешний WB `warehouseId` не создаёт физический остаток и не меняет physical warehouse без binding.
- Один и тот же on-hand не публикуется как независимый полный остаток нескольких складов.
- Warehouse-level reserve не может превышать available выбранного physical warehouse.
- Если on-hand есть только на другом складе, документ не стартует молча: выдаётся typed conflict с
  найденным складом и допустимым следующим действием.
- Warehouse switch после активного резерва, pick, pack или box binding не выполняется как field edit;
  требуется release/re-reserve либо отдельный transfer process.
- При `address_storage_enabled=false` оператор не выбирает cell; система использует утверждённую
  default operational location.
- Короб не создаёт остаток сам по себе; его warehouse выводится из операции, а location описывает
  текущее место, если оно реально отслеживается.
- Cancellation/undo не возвращает товар в другой warehouse; destination location задаётся oracle.
- Любая выдача списков и операции остаются tenant-scoped; доступ к физическим складам не расширяется
  из-за знания UUID/barcode.

## 9. Вопросы, обработанные и переданные дальше

Это не блокеры S03: факты, альтернативы и владельцы решения известны. До Product/Architecture verdict
разработка не начинается.

| ID | Вопрос | Почему нельзя решить исследователю | Владелец / стадия |
|---|---|---|---|
| Q-01 | Что именно считается количеством физических складов: все `warehouses` или только typed physical/active/authorized? | Определяет product taxonomy и migration | Product S07 + Architect S13 |
| Q-02 | Может ли несколько WB seller warehouses одного seller ссылаться на один physical warehouse? | Нужна mapping cardinality и stock-publication policy | Product S07 + Architect S13 |
| Q-03 | При `address_storage_enabled=false` допустим ли ship/post через `__SORTING__` без явной ячейки? | Конфликт BLG-I10 с текущим DEC-019 | Product S07 |
| Q-04 | При address storage on отсутствие cell блокирует только pick или также final ship, если фактический scan/box already proves quantity? | Бизнес-оракул, не технический факт | Product S07 |
| Q-05 | Если товар есть на другом складе: только блокировать и предложить transfer, разрешать смену до reserve или автоматически переносить? | Автоперенос имеет data/concurrency risk | Product S07 + Architect S13 |
| Q-06 | Нужен отдельный barcode склада или scan любой cell одновременно выбирает её warehouse? | Влияет на scanner namespace и оборудование | Process S05 + Product S07 |
| Q-07 | Куда возвращает stock отмена: исходная cell, sorting текущего warehouse или configurable return zone? | Нужен единый cancel/return oracle | Product S07 |
| Q-08 | Нужна ли per-user/per-role warehouse assignment при нескольких physical warehouses? | Это authorization surface | Product S07 + Architect S13 |
| Q-09 | Является ли `WarehouseBox.storage_location_id` только координатой или обязательной частью адресного учёта? | Определяет shipment gate и migration | Product S07 |

## 10. Проверенная неприменимость

- Новый marketplace API, endpoint, webhook или polling loop не вводится. Используемый WB-контракт
  только подтверждает семантику external `warehouseId`; изменение API WB находится вне BLG-I10.
- Статусный автомат заказов WB, Честный знак, формат маркировки и печатные шаблоны не меняются.
  Они только потребляют уже разрешённый warehouse context.
- Межскладское перемещение не проектируется в S03; оно является допустимым downstream действием при
  warehouse conflict, но не автоматическим fallback.
- Макеты и UI-компоненты не создаются на S03. Поверхности перечислены для будущего process/UX scope.
- Production data repair, merge, deploy, push и операции с внешними WB/Ozon системами не выполнялись.

## 11. S03 exit check

- [x] Scope нового модуля ограничен warehouse/location context.
- [x] Операционный путь от приёмки до отгрузки и возврата остатка покрыт.
- [x] Каталог, остаток, резерв, FBS order/supply, picking, packing, marking/print consumption и boxes
  классифицированы.
- [x] WB external warehouse contract отделён от WMS physical warehouse.
- [x] Competitor workflows/screens исследованы по официальной документации Odoo и Microsoft.
- [x] Tenant/roles, batch volume и degraded mode обработаны.
- [x] Каждый claim имеет источник, дату/версию и evidence level.
- [x] Все hypothesis/decision rows имеют downstream owner.
- [x] `unhandled_applicable_rows = 0`.
- [x] Оснований для `S03_BLOCKED` нет; dossier готов к независимому `S04 RESEARCH_CRITIC`.
