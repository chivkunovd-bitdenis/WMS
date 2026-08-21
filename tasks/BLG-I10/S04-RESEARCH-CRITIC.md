# BLG-I10 - S04 RESEARCH_CRITIC

## Паспорт

- Роль: `pipeline-reviewer`, независимый `research-critic`.
- Модельный класс: `gpt-5.6-sol`, `expensive`.
- Дата проверки: `2026-08-21`, Europe/Moscow.
- Проверенный вход: `MODULE-DOSSIER.md`, backlog I10, warehouse/location/FBS binding, stock
  availability, reservation, marking-pool и operator-surface code на baseline.
- Внешние операции: внешние API и live-системы не вызывались; секреты, deploy и production не
  затрагивались.
- Verdict: `RESEARCH_REWORK`.

## Итог критика

S03 правильно отделяет физический WMS-склад от внешнего WB `warehouseId`, подтверждает принадлежность
ячейки одному складу и находит реальную причину инцидента: auto-created `FBS WB <id>` стал обычным
WMS-складом со своей `__SORTING__`, а FBS-заказы, резервы и поставки закрепились за ним.

Но research пока нельзя пропустить в S05. Предлагаемая модель не закрывает самую опасную часть
перехода: один физический остаток нельзя без allocation policy опубликовать полным объёмом в несколько
WB seller warehouses. Кроме того, существующие `FBS WB` склады уже содержат операционное состояние и
не могут быть просто скрыты или переклассифицированы. Capability matrix считает эти области
обработанными, хотя для них нет отдельных строк и проверяемых downstream obligations.

## Блокирующие находки

### RC-01 - many-to-one binding создаёт риск двойной продажи одного физического остатка

S03 оставляет cardinality вопросом Q-02 и описывает внешний mapping в CAP-13, но этого недостаточно.
Сейчас модель и service намеренно запрещают одному seller связать два WB `warehouseId` с одним
`wms_warehouse_id` (`uq_fbs_warehouse_bindings_seller_wms_warehouse` и
`wms_warehouse_already_bound`). При этом stock sync для каждого binding независимо вычисляет один и тот
же `storage + sorting - outbound reservations - FBS reservations` физического склада и публикует
полученное абсолютное количество в WB.

Если снять ограничение 1:1 без отдельного stock-allocation contract, остаток 10 может быть опубликован
как 10 в каждом из двух WB-складов. Локальные FBS-резервы затем действительно конкурируют за общий
warehouse-level pool, но WB уже может принять суммарный спрос 20. Нужны отдельные capability rows для:

1. cardinality `WB seller warehouse -> physical WMS warehouse`;
2. распределения publishable stock между WB `warehouseId` или явно запрещённого many-to-one;
3. единого reserve/availability pool и конкурентных заказов из разных WB-складов;
4. zeroing/republication обоих внешних складов при remap, disable и rollback.

До этого CAP-02/CAP-13 и Q-02 не закрывают contract, а инвариант «один on-hand не публикуется полным
остатком нескольких складов» остаётся декларацией без capability owner.

Источники: `backend/app/models/fbs_warehouse_binding.py:28-65`,
`backend/app/services/fbs_warehouse_binding_service.py:72-91,129-190`,
`backend/app/services/fbs_stock_sync_service.py:487-534`,
`backend/app/services/fbs_stock_availability_service.py:20-155`,
`backend/app/services/wb_marketplace_orders_service.py:516-570`.

### RC-02 - технические `FBS WB` склады нельзя просто скрыть

S03 предлагает тип `physical | integration_projection` и исключение integration warehouses из
операторского счётчика. Но текущий auto-FBS warehouse уже не является чистой проекцией: на него
ссылаются `FbsOrder`, `FbsOrderReservation`, `FbsSupply`, `StorageLocation`, `InventoryBalance` и stock
sync binding. Именно на таком складе в инциденте лежали 519 единиц.

Research не сравнивает безопасные варианты перехода и не содержит capability rows для inventory
reconciliation, переноса/сохранения активных резервов, незавершённых supply/pick/pack/box документов,
истории движений, stock-sync items, zeroing старого WB binding, idempotent retry и rollback. Простое
скрытие создаст невидимый остаток, а простая смена binding не перепривяжет уже созданные orders и
supplies. Текущий binding service блокирует remap только при активном FBS reserve на старом складе и
не доказывает безопасность остальных ссылок.

Нужна отдельная capability family `legacy_auto_fbs_warehouse_migration` со scope discovery, правилами
merge/deactivate, preconditions, dry-run counts, конфликтами, повторным запуском и post-migration
инвариантами. До её появления `unhandled_applicable_rows = 0` неверен.

Источники: `backend/app/services/wb_marketplace_orders_service.py:275-357`,
`backend/app/models/fbs_order.py:177-202,359-388`, `backend/app/models/fbs_supply.py:33-63`,
`backend/app/services/fbs_warehouse_binding_service.py:145-167,194-214`, backlog I10 lines 664-668.

### RC-03 - поведение скана ячейки противоречит исходному требованию

Backlog I10 говорит: скан склада переключает склад, а скан ячейки выбирает ячейку внутри текущего
склада. CAP-06 формулирует другое поведение: barcode ячейки одновременно выбирает её owning warehouse
и location. Это может молча переключить физическую площадку после того, как оператор открыл документ
или сформировал резерв.

Такой выбор нельзя оставлять строкой со статусом `gap`. Нужна `decision_required` capability с
явными альтернативами: cross-warehouse cell scan блокируется typed conflict; разрешён только до
stock commitment; либо выполняет подтверждаемую смену с release/re-reserve. Отдельно нужно описать
barcode склада, barcode ячейки текущего склада, barcode чужого склада, stale/deactivated location и
collision с box/product barcode.

Источники: backlog I10 lines 684-692, `backend/app/models/storage_location.py:22-51`,
`MODULE-DOSSIER.md` CAP-06/CAP-07 и Q-06.

### RC-04 - не определён владелец складского контекста и граница его смены

S03 перечисляет весь путь товара, но не отвечает, где живёт current warehouse: в operator session,
устройстве/ТСД, открытом workspace, order, supply или shipment document. Это критично для двух вкладок,
двух операторов, повторного входа, смены default warehouse, деактивации склада и scan после появления
резерва. Backlog требует selector только в сортировке и отгрузке, тогда как dossier расширяет
warehouse context на приёмку, подбор, упаковку, маркировку и короба без отдельной process-boundary
матрицы.

Нужны capability rows для context source-of-truth и наследования по цепочке
`inbound -> sorting -> pick -> pack/mark -> box -> ship`, а также разрешённых точек switch. Уже
заявленный инвариант про запрет field edit после reserve/pick/pack должен иметь собственный owner и
cases: до резерва, после резерва, после первого pick, после KIZ reserve/apply, после box binding и при
частичном batch success.

### RC-05 - marking pool и warehouse reserve смешаны в общей строке CAP-18

CAP-18 утверждает, что marking/print только потребляют warehouse context. Фактически marking pool
сейчас tenant/seller/GTIN scoped и не имеет `warehouse_id`; KIZ резервируется на FBS order, а order
имеет отдельный physical warehouse. Поэтому смена склада после reserve/print/apply затрагивает два
разных пула: физический stock reserve и глобальный seller marking-code pool.

Research должен явно решить, остаётся ли marking pool глобальным для seller, какие действия допустимы
после reserve/print/apply, как отмена/remap освобождает или сохраняет KIZ и должен ли printed physical
label иметь location trace. Это не означает, что пул надо делить по складам, но его warehouse
неприменимость должна быть доказанной строкой, а не подразумеваться. Аналогично отдельной строкой
должно быть проверено, что box warehouse наследуется от owning operation и не меняется из-за
nullable `storage_location_id`.

Источники: `backend/app/models/marking_code.py:82-112,216-260`,
`backend/app/services/fbs_marking_service.py:459-493`,
`backend/app/services/fbs_workspace_service.py:479-518`, `backend/app/models/warehouse_box.py:18-46`.

## Что подтверждено без rework

- Physical WMS warehouse и WB `warehouseId` действительно являются разными идентичностями.
- Location tenant-unique по barcode и принадлежит ровно одному warehouse.
- FBS warehouse-level reserve и physical availability уже считаются в одном WMS warehouse.
- `__SORTING__` является location внутри warehouse, а не межскладским pool.
- В one-warehouse UX можно скрывать selector только после определения множества active, physical и
  authorized warehouses; общий `GET /warehouses` сейчас такого различия не делает.
- Nullable box location сама по себе не должна создавать новый warehouse identity.

## Условие снятия blocker

Автор S03 должен обновить dossier и capability matrix так, чтобы:

1. many-to-one mapping был либо запрещён как продуктовый инвариант, либо имел allocation/publish/
   reserve contract, исключающий двойную публикацию одного остатка;
2. существующие auto-created `FBS WB` warehouses получили отдельную migration/reconciliation family
   с активными orders, reserves, supplies, locations, balances, boxes и sync state;
3. cross-warehouse cell scan стал явным decision row и не мог молча переключать склад после stock
   commitment;
4. source-of-truth складского контекста и разрешённые switch boundaries были представлены отдельными
   capability rows по всему пути товара;
5. marking-code pool, physical stock reserve и box inheritance были разделены и получили доказанную
   warehouse applicability/non-applicability.

После rework нужен новый независимый S04. До выполнения этих условий `RESEARCH_PASSED` запрещён.
