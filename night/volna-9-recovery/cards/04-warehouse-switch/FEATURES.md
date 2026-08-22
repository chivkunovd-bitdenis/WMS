ФИЧ: 13

## Фичи

### 1. Операционный склад и разрешение складского штрихкода

Оператор получает в API только физически пригодные для работы склады, а сервер отличает штрихкод склада от штрихкода ячейки. Добавить `warehouses.is_operational` и сгенерированный `warehouses.barcode`; миграцией пометить legacy `fbs-wb-*` / `FBS WB *` служебными. Резолвер обязан отвергать коллизию с кодом или штрихкодом ячейки и неоднозначный код, а не выбирать результат по приоритету.

Файлы:

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/app/models/warehouse.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/alembic/versions/<revision>_warehouse_operational_barcode.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/app/api/warehouses.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/tests/test_warehouses.py`

Зависит от: принятого `04-A` (вливания `fix/warehouse-single-20260821`).

Проверка: миграция оставляет один «Основной» операционным, а `FBS WB *` — служебным; список выбора не содержит служебных строк. Штрихкод склада возвращает тип `warehouse`, баркод ячейки — тип `location`; коллизия и чужой tenant возвращают понятную ошибку без смены контекста.

### 2. Привязка WB и FBS-preflight работают только с операционными складами

Сервис не позволяет активной WB→WMS-привязке ссылаться на служебный склад. Preflight считает общий свободный остаток только по операционным складам tenant, рекомендует склад с наибольшим покрытием (при равенстве — текущий) и возвращает агрегированные строки: нехватка на складе консолидации — предупреждение, общая нехватка — блокировка.

Файлы:

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/app/services/fbs_warehouse_binding_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/app/services/fbs_stock_availability_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/app/services/fbs_supply_validator_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/tests/test_fbs_stock_availability.py`

Зависит от: 1, принятого `04-A`.

Проверка: товар только на другом операционном складе даёт одну агрегированную предупреждающую разбивку и не блокирует создание; суммарная нехватка блокирует его с количеством дефицита. Остатки служебного склада не участвуют ни в одном из результатов.

### 3. Неразблокированная FBS-поставка принимает склад консолидации

До первого подбора, создания короба или упаковки API позволяет выбрать операционный склад консолидации и фильтрует FBS-списки по физическому WMS-складу. После первого действия сервер запрещает смену с причиной «Склад закреплён: подбор уже начат»; экранный фильтр не переписывает склад исторического документа.

Файлы:

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/app/api/fbs_supplies.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/app/services/fbs_supply_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/tests/test_fbs_supply_from_orders.py`

Зависит от: 1, 2, принятого `04-A`.

Проверка: новую поставку можно создать на рекомендованном или вручную выбранном операционном складе; до первого действия склад меняется, после — тот же запрос отклоняется. При переключении списка существующая поставка сохраняет собственный `warehouse_id`.

### 4. Канонические WarehouseContextSwitch и WarningNotice

В frontend ui-kit появляются два повторно используемых компонента: `WarehouseContextSwitch` принимает только подготовленный список операционных складов и скрывается при 0–1 варианте; `WarningNotice` показывает неблокирующее предупреждение. Компоненты покрывают обычное, раскрытое, загрузочное, недоступное и ошибочное состояния без кодов, UUID и остатков в выборе.

Файлы:

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/ui-kit/WarehouseContextSwitch.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/ui-kit/WarningNotice.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/ui-kit/index.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/ui-kit/WarehouseContextSwitch.test.tsx`

Зависит от: нет; использовать на экранах только после 1.

Проверка: при одном варианте компонент не рендерится; при двух выбор открывается по клику, показывает только имена и закрывается после `onChange`. В loading/error/disabled состоянии действие недоступно и причина видна оператору.

### 5. Единый сессионный контекст склада в приложениях ФФ и селлера

Приложения хранят выбранный операционный склад до logout, автоматически выбирают единственный или первичный операционный склад и очищают контекст при выходе. В данные и формы больше не попадает `list[0]` или служебный `FBS WB *`; селлерский контекст остаётся только значением своей заявки, не глобальным фильтром портала.

Файлы:

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/utils/fbsWarehouse.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/contexts/WarehouseContext.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/App.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/apps/seller/SellerApp.tsx`

Зависит от: 1, 4, принятое `04-A`.

Проверка: при одном операционном складе форма получает его без выбора; при двух переключение сохраняется между экранами одной сессии; logout и последующий login не наследуют чужой выбор.

### 6. Контекст склада на товарах и синхронизации остатков WB

На S-01 контекст фильтрует только складские количества товара, а на S-04 — показанную разбивку и привязки выбранного операционного склада. Смена не добавляет колонку склада, не меняет свойства товара и не публикует/перераспределяет остаток WB.

Файлы:

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/sections/CatalogSection.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/FfFbsStockSyncScreen.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/tests-e2e/ff-fbs-stock-sync.spec.ts`

Зависит от: 1, 4, 5, принятое `04-A`.

Проверка: при переключении S-01 меняются только остатки выбранного склада; S-04 показывает данные выбранного операционного склада и не вызывает публикацию остатка. При нуле складов отображается `EmptyState` с просьбой добавить рабочий склад.

### 7. Контекст задаёт приёмку и отгрузку без второго выбора в форме

На S-22 и S-24 строка выбора стоит под заголовком до зависимых данных, задаёт склад нового документа и набор ячеек. Открытый исторический документ показывает свой склад, а возврат в список восстанавливает сессионный контекст; отдельное поле «Склад для заявки/отгрузки» удаляется.

Файлы:

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/InboundScreen.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/OutboundScreen.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/tests-e2e/inbound-intake.spec.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/tests-e2e/outbound-submit-storage.spec.ts`

Зависит от: 1, 4, 5.

Проверка: оператор с двумя складами меняет контекст до создания и видит только его ячейки; созданный документ хранит этот склад. При одном операционном складе строка и второе поле отсутствуют.

### 8. Контекст на перемещениях и честное отображение пары transfer

S-25 фильтрует строки текущим складом. Для межскладского подбора одна понятная операция «из склада / в склад» раскрывает техническую пару; при фильтре одного склада видна его сторона, без UUID и без ручного transfer order.

Файлы:

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/TransfersScreen.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/tests-e2e/transfer-and-outbound.spec.ts`

Зависит от: 4, 5; отображение межскладской пары — также от 11.

Проверка: обычные перемещения фильтруются сменой контекста; после кросс-складского pick одна строка раскрывает обе стороны, а в одном складском фильтре остаётся соответствующая сторона.

### 9. Preflight FBS-поставки объясняет, а не прячет межскладской подбор

Диалог создания FBS-поставки показывает рекомендованный склад и позволяет выбрать другой до создания. Он использует `WarningNotice` для одной агрегированной неблокирующей разбивки «нужно / здесь / взять со склада», `ErrorNotice` для общей нехватки и скелет с причиной блокировки во время проверки.

Файлы:

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/fbsApi.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/FbsSupplyCreateDialog.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/FbsSupplyCreateDialog.test.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/tests-e2e/ff-fbs-supply.spec.ts`

Зависит от: 2, 3, 4, 5, принятое `04-A`; финально приземлять после 02 и 06 из-за горячего `FfFbsSupplyWorkspace.tsx`/`fbsApi.ts`.

Проверка: локальная нехватка при достаточном общем остатке оставляет «Создать поставку» доступной и показывает один `WarningNotice`; общая нехватка блокирует кнопку с объяснением. После фонового обновления список notices не исчезает и устаревший preflight не создаёт поставку.

### 10. FBS-списки и рабочее место показывают контекст, склад документа и блокировку смены

На S-03 список фильтруется по WMS-складу, отдельно от существующего фильтра WB. В рабочем месте переключатель стоит до `ScannerLine`: незапущенная поставка может сменить склад консолидации, начатая показывает имя и недоступное действие с причиной; пустой выбранный склад даёт табличный `EmptyState`, не новую колонку в «Новых».

Файлы:

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/FfFbsOrdersScreen.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/FfFbsSupplyWorkspace.test.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/tests-e2e/ff-fbs-supply.spec.ts`

Зависит от: 3, 4, 5, 9; выполнить после 02 и 06, а в `FfFbsOrdersScreen.tsx` — после 05 → 02.

Проверка: смена контекста перезагружает только данные выбранного WMS-склада и не смешивает их с WB-фильтром. Поставка до первого действия меняет консолидацию, после него показывает недоступное объяснение; пустой склад показывает следующий шаг оператору.

### 11. Кросс-складской FBS-pick создаёт атомарную пару движений и убирает упаковочный обход

Подтверждённый подбор из другого операционного склада создаёт в одной транзакции `stock_transfer_out` из фактической ячейки и `stock_transfer_in` в сортировку склада консолидации с общим `transfer_group_id`, фактическими `seller_id` и `warehouse_id`. Повтор ключа скана возвращает прежний результат, undo создаёт обратную полную пару; упаковка списывает только из сортировки и больше не ищет чужую ячейку молча.

Файлы:

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/app/services/fbs_picking_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/app/services/inventory_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/app/services/fbs_packaging_integration_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/tests/test_fbs_picking.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/tests/test_fbs_packaging_integration.py`

Зависит от: 1, 3, внешних принятых 07-A и 06; выполнять после 02 и 06 по обязательному порядку `ARCH-CROSS.md`.

Проверка: scan ячейки другого операционного склада + scan товара создают ровно одну связанную пару, а повтор не создаёт вторую. Undo оставляет обратную пару и не половину переноса; упаковка без подтверждённого pick не может списать товар из чужой сортировки.

### 12. Сканер рабочего места переключает склад или ячейку без неявного pick

FBS-рабочее место вызывает resolver: скан склада меняет контекст и сбрасывает ячейку, скан ячейки выбирает её родительский склад и саму ячейку, скан товара не меняет место. `ScannerLine` всегда говорит, какой следующий скан ожидается; ошибочный, чужой, пустой или неоднозначный скан оставляет склад, ячейку и остаток прежними, а успешный pick показывает единственную строку «Взято: Склад / ячейка».

Файлы:

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/fbsApi.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/ui-kit/ScannerLine.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/tests-e2e/ff-fbs-supply.spec.ts`

Зависит от: 1, 5, 10, 11; выполнять после 06.

Проверка: скан склада меняет только склад, скан ячейки другого склада меняет склад и ячейку, а скан товара — только подтверждает текущий pick. Ошибка не меняет экранное состояние; сетевой повтор возвращает прежнюю строку «Взято…» без отдельного диалога.

### 13. Селлер выбирает склад только в собственной заявке

В S-26 нет глобального переключателя. В новой заявке S-29 выбор операционного склада виден только при двух и более доступных вариантах; S-28 показывает и разрешает менять склад лишь у черновика, после передачи — только текст документа. В интерфейс и ответы для селлера не попадают служебные склады, технические коды и количественная разбивка чужих складов.

Файлы:

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/SellerDocumentsScreen.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/SellerInboundDraftScreen.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/sellerInboundDocumentUi.test.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/tests-e2e/seller-cabinet.spec.ts`

Зависит от: 1, 4, 5.

Проверка: при одном операционном складе поля нет; при двух селлер видит только имена доступных складов и сохраняет выбор в черновике. После передачи редактирование недоступно, а список документов не фильтруется глобальным контекстом ФФ.

## Порядок

Сначала обязательная база вне этой нарезки: принять `04-A` из `fix/warehouse-single-20260821`; до касания горячего S-03 также должны быть влиты 03, затем 01, затем выполнены 02 и 06 в порядке карты волны.

После `04-A` можно параллельно делать 1 и 4. Затем 2 и 5 зависят от 1/4 и также не пересекаются. После 5 параллельны 6, 7, 8 и 13; 8 может выйти раньше создания transfer-пары, но её раскрытие пары ждёт 11. Фича 3 следует за 1 и 2. Фича 9 следует за 2, 3, 4 и 5. Фича 10 идёт после 9 и после 02/06/05 по горячим файлам. Фича 11 начинается только после принятых внешних 07-A и 06, а также после 02; затем 12 завершает сканерный поток поверх 10 и 11.

## Что осталось за бортом

- Географически разнесённые площадки, физическая перевозка и отдельные transfer orders не входят в контракт: здесь склады — зоны одной площадки.
- Новый экран, пункт меню, колонка склада в таблице «Новые», серверный профиль рабочего места и ручной ввод баркодов склада намеренно не создаются.
- Отчётность, хранение и биллинг не изменяются этой карточкой; их зависимость от неизменяемого `InventoryMovement.warehouse_id` обеспечивает внешняя 07-A.
- Мобильный ТСД требует отдельного исполнителя и проверки по `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/mobile/docs/PROGRESS.md`: этот каталог не назван в контракте как часть frontend-реализации карточки.
- Секреты, ключи, токены, `.env`, кабинеты учётных данных и боевой прод `194.87.96.144` не открывались и не изменялись.
