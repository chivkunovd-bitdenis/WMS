# Практический S0 owner contract: встраивание Ozon в текущий WMS

Статус: ROOT PRODUCT VALIDATION v3 — принято 44/44, 2026-08-24

## Граница и правило исследования

Этот документ сохраняет только принятые владельцем ответы для S0. Единственное нормативное продуктовое основание — [OWNER_FINAL_PROMPT.txt](OWNER_FINAL_PROMPT.txt): если работа с Ozon не имеет доказанного обязательного отличия, текущий экран, действие и физический процесс WMS не меняются. [OZON_OFFICIAL_PROCESS_DELTA_MATRIX.md](OZON_OFFICIAL_PROCESS_DELTA_MATRIX.md) использована только как индекс официальных фактов и прямых ссылок, но не как UI-требование.

Старые `ARCH`, `REUSE_MAP`, макеты, прототипы, тесты и run-артефакты отвергнуты и не являются источниками требований. `UNKNOWN` в этом контракте всегда означает: UI остаётся без изменений, а внешняя операция блокируется, если без неизвестного факта её нельзя выполнить безопасно. Никакой новый control из `UNKNOWN` не выводится.

Реальные записи остатков Ozon FBS с тестовым аккаунтом запрещены. Разрешены только fake/contract tests без внешней записи в Ozon.

## Вопросы

Ниже находятся ровно 44 принятых практических вопроса и ответа. В каждом ответе отдельно указаны текущий baseline, продуктовое решение владельца и наличие либо отсутствие официальной необходимости.

## Изученные источники с прямыми ссылками

### Нормативный owner source

- [OWNER_FINAL_PROMPT.txt](OWNER_FINAL_PROMPT.txt) — единственное нормативное продуктовое заявление владельца.

### Первичные официальные источники Ozon

- [Ozon Seller API](https://docs.ozon.ru/api/seller/) — официальный корень документации Seller API.
- [Схема FBS Стандарт](https://docs.ozon.ru/api/seller/#section/Upravlyajte-zakazami-FBO-FBS-i-rFBS/Shema-FBS-Standart) — официальный процесс FBS.
- [Собрать заказ, версия 4](https://docs.ozon.ru/api/seller/#operation/PostingAPI_ShipFbsPostingV4) и [частичная сборка отправления, версия 4](https://docs.ozon.ru/api/seller/#operation/PostingAPI_ShipFbsPostingPackage) — posting, товары и package-операции.
- [Создать задание на формирование этикеток](https://docs.ozon.ru/api/seller/#operation/PostingAPI_CreateLabelBatchV2) — официальный print asset для FBS.
- [Сборка заказов FBS](https://seller-edu.ozon.ru/fbs/ozon-logistika/sobrat-zakazy-fbs), [требования к упаковке](https://seller-edu.ozon.ru/fbs/ozon-logistika/trebovaniya-k-upakovke) и [документы для отгрузки](https://seller-edu.ozon.ru/fbs/ozon-logistika/logistics-docs) — официальные физические действия и передача.
- [Схема FBO](https://docs.ozon.ru/api/seller/#section/Upravlyajte-zakazami-FBO-FBS-i-rFBS/Shema-FBO) и [создание и заполнение заявки на поставку](https://seller-edu.ozon.ru/fbo/process-details/fill-in-application-form) — официальный процесс поставки, место и интервал.
- [Работа с транспортными грузоместами в поставках FBO](https://dev.ozon.ru/start/525-Rabota-s-transportnymi-gruzomestami-TGM-v-postavkakh-FBO/) и [интеграция Seller API FBO со сканером](https://dev.ozon.ru/start/526-Gaid-integratsiia-metodov-Seller-API-FBO-so-skanerom/) — официальные GM/TGM-сущности и capability-dependent операции.
- [Новые beta-методы для актов FBO](https://dev.ozon.ru/news/781-Novye-beta-metody-dlia-raboty-s-aktami-FBO-v-Seller-API/) — официальное свидетельство capability, но не универсального operator control.

Ограничение проверки: интерактивные страницы Ozon в текущем исследовательском окружении не вернули пригодный для независимого повторного чтения текст. Поэтому конкретные официальные утверждения ниже ограничены фактами из разрешённого fact index; недостающие account-, posting- и supply-specific детали не реконструируются и остаются `UNKNOWN`.

### Текущий WMS baseline по коду

- [SellerApp.tsx](../../frontend/src/apps/seller/SellerApp.tsx), [sellerPermissions.ts](../../frontend/src/utils/sellerPermissions.ts) и [SellerSettingsScreen.tsx](../../frontend/src/screens/v2/SellerSettingsScreen.tsx) — существующий route `/seller/settings`, текущая карточка WB и действующая seller-side граница permission `settings`.
- [App.tsx](../../frontend/src/App.tsx) — текущие FF routes и permission boundaries: `/app/ff/fbs/stock-sync` доступен только при `isFulfillmentAdmin`, а в FF catalog передаётся `canManageCatalog={isFulfillmentAdmin}`.
- [FfProductsCatalogScreen.tsx](../../frontend/src/screens/v2/FfProductsCatalogScreen.tsx) — единый каталог, существующая filter bar, общие физические поля и редактирование общего `Остаток FBS`, защищённое `canManageCatalog`.
- [FfFbsStockSyncScreen.tsx](../../frontend/src/screens/v2/FfFbsStockSyncScreen.tsx) и [FbsStockAllocationDialog.tsx](../../frontend/src/screens/v2/FbsStockAllocationDialog.tsx) — текущий `Склад WMS`, toggle/manual sync, status/error/last sync и ручное распределение общего пула по binding.
- [fbs_warehouse_binding_service.py](../../backend/app/services/fbs_warehouse_binding_service.py), [fbs_stock_availability_service.py](../../backend/app/services/fbs_stock_availability_service.py) и [wb_marketplace_orders_service.py](../../backend/app/services/wb_marketplace_orders_service.py) — лимит общего FBS-пула, `allocated_elsewhere`, доступность и атомарный резерв.
- [FfFbsOrdersScreen.tsx](../../frontend/src/screens/v2/FfFbsOrdersScreen.tsx) и [FfFbsSupplyWorkspace.tsx](../../frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx) — одна очередь FBS, существующие filters/selection errors и четыре этапа workspace.
- [FfSuppliesShipmentsPage.tsx](../../frontend/src/screens/ff/FfSuppliesShipmentsPage.tsx) — текущий marketplace shipment document и этапы `Товары → Подбор → Упаковка`.
- [FfInboundQueuePage.tsx](../../frontend/src/screens/ff/FfInboundQueuePage.tsx) и [SellerDocumentsScreen.tsx](../../frontend/src/screens/v2/SellerDocumentsScreen.tsx) — текущий общий поток документов приёмки/возврата.

Baseline наблюдался в текущей ветке на момент исследования; это чтение кода, не browser acceptance и не production evidence.

## Подтверждённые факты

- В WMS уже есть единые операторские поверхности для настроек селлера, каталога, FBS-заказов, FBS-остатков, marketplace shipment и возвратов.
- Текущий FBS stock process двухуровневый: общий `Остаток FBS` товара задаёт максимум, затем оператор вручную распределяет его по конкретным external-warehouse bindings. Сумма allocation ограничена через `allocated_elsewhere`.
- Резерв FBS выполняется после блокировки product/reservation rows и уменьшает доступный общий остаток; эта атомарность является baseline-инвариантом.
- Текущий FBS workspace содержит ровно четыре этапа: `Состав → Подбор → Упаковка и маркировка → Короба`.
- Текущий marketplace shipment document содержит ровно три этапа: `Товары → Подбор → Упаковка`, использует существующие cells, PackagingTask и WMS boxes.
- Текущий actor split уже задан routes и permissions: seller owner/admin с действующим seller permission `settings` управляет marketplace connection в `/seller/settings`; FF admin управляет общим FBS pool, warehouse allocations и publication на существующих FF-поверхностях.
- `/app/ff/fbs/stock-sync` защищён условием `isFulfillmentAdmin`. Редактирование общего `Остаток FBS` в FF catalog защищено `canManageCatalog`, причём текущий `App.tsx` передаёт туда `isFulfillmentAdmin`.
- Официальные Ozon-источники подтверждают отдельные posting/package/label и GM/TGM identities, но само наличие API-сущности не доказывает необходимость нового экрана или кнопки.
- Для Ozon FBS собственная provider label является доказанным внешним asset; она допустима только в текущей print zone.

## Текущий WMS baseline

S0 встраивается в существующую топологию. Ozon connection остаётся в `/seller/settings` и принадлежит seller owner/admin с действующим permission `settings`. Каталог остаётся одним WMS catalog. Общий sellable FBS maximum, per-binding allocations и publication принадлежат FF admin и остаются в существующих FF screens: limit — в FF catalog через `canManageCatalog`, bindings/publication — в `/app/ff/fbs/stock-sync`, защищённом `isFulfillmentAdmin`. WB и Ozon заказы входят в одну `/app/ff/fbs` queue и проходят тот же workspace. FBO остаётся одним текущим marketplace shipment document. Возвраты остаются в существующей очереди и текущем процессе приёмки. Seller self-service surface или permission для управления stock в S0 не вводится.

## Роли и границы ответственности S0

- **Seller owner/admin:** подключает и обслуживает Ozon только в существующем `/seller/settings` с текущим seller permission `settings`. Эта роль не получает управление общим FBS pool, allocations или publication.
- **FF admin:** в существующих FF screens задаёт общий catalog `Остаток FBS`, распределяет его по external-warehouse bindings и управляет publication. Route `/app/ff/fbs/stock-sync` уже ограничен `isFulfillmentAdmin`; редактирование limit в FF catalog уже ограничено FF-side `canManageCatalog`.
- **Запрещённое расширение S0:** seller self-service stock control был бы новой permission и новой surface. Он не вводится; существующие seller screens и permissions для stock не расширяются.

## Принятые вопросы и ответы

### 1. Где подключается Ozon?

- **Baseline:** В текущем `/seller/settings` уже находится компактная карточка подключения Wildberries; integration content показывается по действующему seller permission `settings`, отдельного marketplace settings dashboard нет.
- **Решение владельца:** Seller owner/admin подключает Ozon компактной карточкой только в существующем `/seller/settings`, без нового экрана, dashboard или FF-side connection surface.
- **Official necessity/evidence:** Официальные источники подтверждают необходимость account credentials для Seller API, но не требуют отдельной WMS-поверхности; новый UI не доказан.

### 2. Может ли один seller одновременно работать с WB и Ozon?

- **Baseline:** Один WMS seller уже является владельцем каталога, остатков и складских документов; marketplace сейчас WB-specific.
- **Решение владельца:** Один и тот же seller одновременно может иметь WB- и Ozon-подключение.
- **Official necessity/evidence:** Это продуктовое решение владельца; официального требования Ozon разносить marketplaces по разным WMS sellers нет.

### 3. Сколько Ozon accounts допускается в S0?

- **Baseline:** Текущая WB-интеграция фактически хранит один набор credentials на seller.
- **Решение владельца:** В S0 допускается один active account на `(seller, marketplace)`; backend-модель должна быть account-scoped, чтобы будущий multi-account не ломал данные, но account selector в S0 не появляется.
- **Official necessity/evidence:** Seller API является account-context API, что обосновывает account scope данных; official evidence не требует multi-account UI в S0.

### 4. Что показывается в Ozon connection card?

- **Baseline:** Существующая WB card показывает состояние подключения, ошибки и синхронизацию без отдельного dashboard.
- **Решение владельца:** Ozon card показывает только connection/error, expiry — только если API его действительно сообщает, last sync/error; dashboard и аналитика не добавляются.
- **Official necessity/evidence:** Ни один изученный официальный источник не доказывает обязательный dashboard. Expiry остаётся conditional на фактическое поле API, иначе UI unchanged.

### 5. Кто может менять Ozon connection?

- **Baseline:** Marketplace credentials в `/seller/settings` доступны seller owner/admin с действующим seller permission `settings`; FF stock routes и FF admin permissions не являются доступом к seller connection.
- **Решение владельца:** Менять Ozon connection может только seller owner/admin в существующем `/seller/settings` и только в рамках текущего permission `settings`. Новая роль, permission или отдельная connection surface не вводится.
- **Official necessity/evidence:** Это WMS access-control решение; официальные Ozon-источники не задают роли внутри WMS.

### 6. Как внешний Ozon warehouse связывается с WMS и что делать с delivery/return point?

- **Baseline:** На `/app/ff/fbs` stock bindings внешний WB warehouse связывается через текущий control `Склад WMS`.
- **Решение владельца:** External warehouse Ozon связывается тем же `Склад WMS`. Delivery point и return point — `UNKNOWN`: без official read-only evidence controls не добавляются, а зависящая от них операция disabled/blocked.
- **Official necessity/evidence:** Официальные Ozon-процессы используют внешние destination/route данные, но доступные источники не доказывают универсальный формат или отдельный обязательный control для конкретного аккаунта.

### 7. Создаётся ли отдельный Ozon catalog?

- **Baseline:** В WMS есть один физический каталог товаров.
- **Решение владельца:** Каталог остаётся один WMS catalog; отдельной Ozon-таблицы или копии товара нет.
- **Official necessity/evidence:** Seller API имеет внешние offers/products, но это не доказывает второй WMS catalog; обязательное отличие покрывается mapping data.

### 8. Как видна связь внешнего offer с WMS product?

- **Baseline:** Текущая catalog table является единой строковой поверхностью WMS product и имеет existing action cell.
- **Решение владельца:** Связь видна через marketplace prefix и mapping state; orphan external offers появляются строками в той же catalog table, без отдельного списка.
- **Official necessity/evidence:** Внешние Ozon identifiers требуют mapping, но официальные источники не требуют отдельного экрана; presentation — owner decision в существующей таблице.

### 9. Какие поля каталога общие, а какие conditional для marketplace?

- **Baseline:** Общими являются SKU, ШК, артикул продавца, размер и WMS stock fields; текущие WB-поля и действия присутствуют в catalog context.
- **Решение владельца:** Общие поля сохраняются. `Артикул WB` conditional и в Ozon context отображается как `SKU Ozon`; category conditional; `nmId` и WB actions для Ozon hidden. Новые колонки не добавляются.
- **Official necessity/evidence:** Официальные Ozon identifiers отличаются от WB, что требует корректного conditional data mapping, но не новой таблицы или постоянной колонки.

### 10. Может ли один WMS product иметь mappings и WB, и Ozon?

- **Baseline:** Физический WMS product является общей единицей каталога и stock.
- **Решение владельца:** Один WMS product может одновременно иметь WB mapping и Ozon mapping.
- **Official necessity/evidence:** Marketplace identifiers различны; official evidence не запрещает связывать их с одной внутренней товарной сущностью. Это owner product contract.

### 11. Сколько Ozon mappings допускается для товара в S0?

- **Baseline:** Текущая модель не имеет принятого Ozon multi-account operator flow.
- **Решение владельца:** В S0 у WMS product один Ozon mapping в одном active account; backend mapping account-scoped. Account selection в UI отсутствует.
- **Official necessity/evidence:** Account scope необходим для непересекающихся external identifiers; необходимость нескольких mappings в одном active account официально не доказана.

### 12. Где фильтровать catalog по marketplace?

- **Baseline:** В catalog уже есть единая existing filter bar с search, seller и category filters.
- **Решение владельца:** В эту же filter bar добавляется marketplace filter с default `Все`; новый panel не создаётся.
- **Official necessity/evidence:** Это owner navigation decision для mixed data; Ozon не предписывает WMS-filter UI.

### 13. Где фильтровать catalog по mapping state?

- **Baseline:** Catalog использует ту же filter bar, а account selector отсутствует.
- **Решение владельца:** Там же используется mapping-state filter `Все / Связан / Не связан / Конфликт`; account в S0 hidden/auto.
- **Official necessity/evidence:** Mapping state нужен для безопасной локальной операции, но official evidence не требует отдельной поверхности или account control.

### 14. Куда ведёт read-only sync при наличии несвязанных Ozon offers?

- **Baseline:** Catalog уже является местом просмотра и создания WMS products.
- **Решение владельца:** После read-only sync действие `Перейти к сопоставлению` открывает тот же catalog с filters `Ozon + Не связан`.
- **Official necessity/evidence:** Read-only импорт внешних offers совместим с Seller API; необходимость нового mapping workspace официально не доказана.

### 15. Какие действия доступны для orphan external offer?

- **Baseline:** У catalog row есть existing action cell; создание товара уже выполняется текущим dialog.
- **Решение владельца:** В existing action cell доступны `Связать с товаром` и `Создать товар`; WMS-only actions disabled до mapping. При ambiguity используются `Выбрать другой товар` и `Оставить несвязанным`, без нового UI family.
- **Official necessity/evidence:** Без однозначного mapping внешняя операция небезопасна; official evidence не задаёт UI. Неопределённость блокирует WMS-only mutation и не порождает control вне существующей зоны.

### 16. Что делает импорт Ozon offer?

- **Baseline:** WMS уже имеет current `Создать товар` dialog и общий product catalog.
- **Решение владельца:** Импорт либо связывает existing WMS product, либо текущий dialog `Создать товар` создаёт WMS product с prefill из read-only Ozon data.
- **Official necessity/evidence:** Внешние offer data могут служить source для prefill, но официальные источники не требуют автоматического создания или отдельного dialog.

### 17. Где хранятся marketplace identifiers и какие поля остаются общими?

- **Baseline:** Физические атрибуты WMS product и stock принадлежат общей внутренней сущности.
- **Решение владельца:** Marketplace identifiers хранятся account-scoped и показываются conditional или в mapping detail; физические WMS fields остаются общими.
- **Official necessity/evidence:** Разные account/provider identifiers требуют scope для корректной адресации API; Ozon не требует дублировать физические WMS fields.

### 18. Разделяется ли физический stock по marketplaces?

- **Baseline:** Физический stock WMS общий для товара и склада.
- **Решение владельца:** Физический stock остаётся общим; Ozon не создаёт параллельный физический остаток.
- **Official necessity/evidence:** Ozon требует публикуемое значение, но не отдельную физическую складскую сущность внутри WMS. Разделение не доказано.

### 19. Как резервировать WB и Ozon orders из общего stock?

- **Baseline:** Текущий сервис блокирует product и reservation rows через `with_for_update`, затем проверяет available quantity и создаёт FBS reservation.
- **Решение владельца:** Резерв остаётся атомарным из common available stock; суммарные marketplace allocations не могут превышать common FBS pool.
- **Official necessity/evidence:** Official APIs не определяют внутреннюю конкуренцию WMS. Атомарность — обязательный локальный safety invariant для предотвращения oversell, а не новый UI.

### 20. Что означает `Остаток FBS` в catalog после добавления Ozon?

- **Baseline:** В существующем FF catalog `Остаток FBS` задаёт верхний sellable limit товара, из которого текущий dialog распределяет quantities по external-warehouse bindings. Редактирование защищено FF-side `canManageCatalog`, а текущий `App.tsx` передаёт его только для `isFulfillmentAdmin`.
- **Решение владельца:** FF admin по-прежнему управляет здесь одним common maximum sellable pool для всех marketplaces. Первый уровень двухуровневого процесса не меняется; seller self-service control или permission для этого limit в S0 не вводится.
- **Official necessity/evidence:** Ozon stock publication не требует отдельного WMS maximum. Отдельный Ozon pool официально не доказан и запрещён owner contract.

### 21. Как управляется публикация stock по external warehouse binding?

- **Baseline:** В существующем FF stock screen current binding имеет toggle публикации, ручную sync action и per-binding allocation; route `/app/ff/fbs/stock-sync` доступен только при `isFulfillmentAdmin`.
- **Решение владельца:** FF admin теми же controls управляет auto/manual publisher и allocation для каждого external warehouse вне зависимости от marketplace. Второй уровень двухуровневого процесса сохраняется точно; seller-side stock permission не добавляется.
- **Official necessity/evidence:** Внешние warehouses требуют адресной публикации, но Ozon не доказывает необходимость новой control topology.

### 22. Где находится mixed WB/Ozon stock operation?

- **Baseline:** Stock bindings находятся на существующем FF route `/app/ff/fbs/stock-sync`, защищённом `isFulfillmentAdmin`; там видны mapping, status/error/last sync и действия публикации.
- **Решение владельца:** FF admin выполняет mixed WB/Ozon stock operation только на этой существующей FF-поверхности. Она минимально переименовывается в `Остатки FBS`, получает marketplace filter и сохраняет те же status/error/last sync; новый экран и seller self-service stock surface не создаются.
- **Official necessity/evidence:** Mixed provider data требует различения источника, но официального требования отдельной Ozon stock page нет.

### 23. Что означает выключить только Ozon publication?

- **Baseline:** На FF admin surface `FbsStockAllocationDialog` хранит quantity на конкретном binding, а WB allocations существуют независимо по своим bindings; доступ к route уже ограничен `isFulfillmentAdmin`.
- **Решение владельца:** FF admin выполняет Ozon-only off в существующем dialog: allocation становится `0` на всех Ozon bindings, а WB allocations остаются без изменений. Seller owner/admin не получает этот stock control.
- **Official necessity/evidence:** Это owner safety semantics. Official evidence не требует общей остановки WB при отключении Ozon.

### 24. Как именно сохраняется защита от oversell?

- **Baseline:** Уровень 1 — общий catalog `fbs_stock_limit`; уровень 2 — ручные quantities по bindings. `allocated_elsewhere` не позволяет их сумме превысить limit, а atomic reserve уменьшает available stock.
- **Решение владельца:** Общий pool, проверка `allocated_elsewhere`, per-binding allocation process и atomic reserve сохраняются без изменения; WB и Ozon используют один safety контур.
- **Official necessity/evidence:** Это подтверждённый WMS invariant. Ozon не предоставляет внешней гарантии против гонки двух marketplaces внутри WMS, поэтому ослаблять локальную защиту нельзя.

### 25. Где появляются WB и Ozon FBS orders?

- **Baseline:** В WMS есть одна current `/app/ff/fbs` queue.
- **Решение владельца:** WB и Ozon orders появляются вместе в этой очереди; Ozon-only queue запрещена.
- **Official necessity/evidence:** Ozon posting совместим с единицей текущей очереди; официального требования отдельного operator workflow нет.

### 26. Как фильтровать общую FBS queue по marketplace?

- **Baseline:** У FBS queue уже есть existing filter bar и status filters.
- **Решение владельца:** В existing filter bar используется marketplace filter с default `Все`.
- **Official necessity/evidence:** Это owner decision для mixed queue; Ozon не задаёт внешний WMS filter.

### 27. Как различать provider в identifier cell?

- **Baseline:** У order row уже есть identifier cell; дополнительная marketplace column отсутствует.
- **Решение владельца:** Используется только текстовый prefix `WB · <id>` или `Ozon · <id>` в existing identifier cell; badge, icon и новая колонка запрещены.
- **Official necessity/evidence:** Различные provider ids должны быть однозначны, но official evidence не требует отдельного визуального компонента.

### 28. Как называется warehouse filter в mixed queue?

- **Baseline:** Текущий filter WB-specific и выбирает внешний seller/WB warehouse.
- **Решение владельца:** Только там, где данные mixed, wording становится generic external marketplace warehouse; геометрия и control остаются прежними.
- **Official necessity/evidence:** Ozon имеет external warehouse context, но не требует иной filter mechanics.

### 29. Как Ozon posting представлен в FBS queue/workspace?

- **Baseline:** Current queue открывает один workspace item с order/product lines.
- **Решение владельца:** Один Ozon posting является одним текущим queue/workspace item и содержит свои lines; нового posting workflow нет.
- **Official necessity/evidence:** Официальные v4 operations подтверждают posting с product lines и quantities. Это data-model mapping, не доказательство новой поверхности.

### 30. Можно ли объединить mixed WB/Ozon selection в одну внешнюю передачу?

- **Baseline:** Existing selection error zone блокирует несовместимые выбранные orders.
- **Решение владельца:** Mixed WB/Ozon selection блокируется в этой же error zone; система не создаёт ложную Ozon carriage и не добавляет modal/control.
- **Official necessity/evidence:** Provider mutations и identifiers несовместимы. Официальные источники не доказывают универсальную Ozon carriage, поэтому mixed external operation запрещена.

### 31. Меняются ли FBS stages для Ozon?

- **Baseline:** Workspace содержит ровно `Состав → Подбор → Упаковка и маркировка → Короба`.
- **Решение владельца:** Для Ozon остаются ровно те же четыре stages, их порядок, существующие cells, scans и actions; новый stage запрещён.
- **Official necessity/evidence:** Официальный Ozon FBS physical process укладывается в текущие этапы. Ни один изученный источник не доказывает обязательный отдельный WMS stage.

### 32. Меняется ли `Честный знак` для Ozon?

- **Baseline:** Marking уже находится в current marking row и этапе `Упаковка и маркировка`.
- **Решение владельца:** `Честный знак` остаётся без изменений. Только posting-required Ozon value может появиться в current marking row и только при официальном proof конкретного posting; иначе UI unchanged и assembly blocked при реальной обязательности.
- **Official necessity/evidence:** Официальный FBS process допускает posting/product-specific mandatory exemplar/marking data. Точные поля аккаунта сейчас `UNKNOWN`; speculative field запрещён.

### 33. Где печатается Ozon FBS label?

- **Baseline:** В packing уже есть existing print zone для текущих order/marking assets.
- **Решение владельца:** Та же print zone выбирает provider label; Ozon posting/package label появляется только там, где официальный API требует его для конкретной операции.
- **Official necessity/evidence:** Ozon официально предоставляет label-generation operation и требует Ozon posting identity для handover. Это доказанный conditional asset, но не новый panel.

### 34. Как выполняется внешняя передача Ozon FBS?

- **Baseline:** Existing action zone содержит `Передать в WB`, а status отображается в current status cell.
- **Решение владельца:** В той же action zone для Ozon используется `Передать в Ozon`; pending confirmation показывается в том же status cell, provider распознаётся тем же textual prefix.
- **Official necessity/evidence:** Ozon требует external assembly/handover mutation и последующее состояние. API-различие доказывает provider adapter/copy, но не новый action zone.

### 35. Когда фиксируется marketplace в текущем FBO document?

- **Baseline:** Marketplace shipment создаётся из selected seller/context в current document flow.
- **Решение владельца:** Marketplace фиксируется при создании текущего FBO document из seller connection/context; новой секции выбора не добавляется.
- **Official necessity/evidence:** Внешняя supply принадлежит конкретному provider account, но official evidence не требует отдельной WMS-секции.

### 36. Какие товары доступны в Ozon FBO document picker?

- **Baseline:** Current `Товары` stage выбирает WMS products для marketplace shipment.
- **Решение владельца:** В Ozon document picker доступны только WMS products, mapped к этому Ozon account.
- **Official necessity/evidence:** External supply lines должны адресовать валидные account-scoped Ozon identifiers; unresolved mapping делает create небезопасным и блокируется без нового control.

### 37. Может ли один FBO document содержать WB и Ozon lines?

- **Baseline:** Один current marketplace shipment document является одной внешней отгрузкой.
- **Решение владельца:** Document provider-homogeneous; WB и Ozon lines вместе запрещены.
- **Official necessity/evidence:** Supply identity, account и mutations принадлежат одному provider. Cross-provider supply официально не существует.

### 38. Что происходит до внешнего создания Ozon FBO supply?

- **Baseline:** Existing document header уже содержит destination/date controls и blocker/error zone.
- **Решение владельца:** External create блокируется до read-only discovery destination/timeslot: `0` options — blocker в existing header, `1` — auto в том же control, `>1` — selector в том же header. `UNKNOWN` не разрешает speculative control.
- **Official necessity/evidence:** Официальный Ozon FBO process подтверждает destination и timeslot data. Конкретные options аккаунта неизвестны до read-only evidence, поэтому mutation blocked.

### 39. Меняется ли физический FBO flow?

- **Baseline:** Current document проходит `Товары → Подбор → Упаковка`, использует WMS cells, PackagingTask и WMS boxes.
- **Решение владельца:** Stages, cells, PackagingTask и WMS boxes остаются без изменений; Ozon-only pick/pack panels запрещены.
- **Official necessity/evidence:** Официальные источники описывают external supply/cargo data, но не иной обязательный физический WMS flow.

### 40. Где печатаются Ozon FBO labels?

- **Baseline:** Packaging имеет current print zone для текущего box/cargo context.
- **Решение владельца:** Та же print zone выбирает provider label для current box/cargo и только после официально подтверждённой readiness конкретной сущности.
- **Official necessity/evidence:** Официальные GM/TGM guides подтверждают provider labels для configured entities; точный набор supply-specific, поэтому до readiness действие blocked, новый panel не создаётся.

### 41. Как S0 обращается с GM/TGM?

- **Baseline:** WMS физически закрывает current boxes; отдельного GM/TGM stage или mandatory grouping control нет.
- **Решение владельца:** Cargo/GM/TGM — `UNKNOWN` и operation-blocking. Сначала нужны read-only rules. Детерминированный mandatory mapping может стать backend intent после current box closure; nondeterministic grouping остаётся blocked. Speculative control запрещён.
- **Official necessity/evidence:** Официальные Ozon sources подтверждают отдельные GM/TGM identities и route/capability rules, но не универсальный операторский click или однозначное grouping для каждого supply.

### 42. Где обрабатываются Ozon returns?

- **Baseline:** WMS имеет одну existing queue документов приёмки/возврата и current filters.
- **Решение владельца:** Returns остаются одной очередью; marketplace filter имеет default `Все`, identifier использует тот же textual prefix.
- **Official necessity/evidence:** Внешний provider identity нужно различать, но официальный Ozon source не доказывает отдельную return queue или новый экран.

### 43. Как Ozon return сопоставляется с WMS product?

- **Baseline:** Возврат должен адресовать existing WMS product и затем использовать текущий stock process.
- **Решение владельца:** Mapping выполняется по account-scoped external identifiers/barcodes. Unresolved mapping остаётся blocked; оператор разрешает его через existing catalog mapping, без return-specific mapping UI.
- **Official necessity/evidence:** Account-scoped identity нужна для однозначности; доступные официальные сведения не доказывают безопасный универсальный fallback при отсутствии mapping.

### 44. Меняются ли reception/return UI и stock rules для Ozon?

- **Baseline:** Current reception/return UI и WMS stock rules уже выполняют физическую приёмку и постановку на остаток.
- **Решение владельца:** UI и stock rules не меняются. Ozon-specific condition inspection — `UNKNOWN` и ничего не добавляет без official proof; если условие обязательно, операция blocked до evidence.
- **Official necessity/evidence:** Изученные официальные источники не подтверждают обязательный дополнительный WMS inspection control для S0.

## Противоречия

- Ozon имеет собственные posting/package/GM/TGM identities, но identity не равна операторскому stage или panel. Owner rule запрещает превращать API-модель в новый UI без доказанного физического действия.
- WB wording текущего baseline не может оставаться неверным в mixed context, но корректировка ограничена conditional text/prefix и не разрешает redesign.
- Ozon label нельзя подменить WB/internal barcode; при этом доказанное отличие локализовано в existing print zone.
- Отдельные marketplace allocations нужны для публикации, но физический stock и catalog `Остаток FBS` остаются одним общим pool. Параллельные provider pools противоречат принятому двухуровневому процессу.
- Seller owner/admin отвечает за connection, а FF admin — за общий pool, allocations и publication. Перенос stock control в seller portal противоречил бы текущим routes/permissions и создавал бы запрещённую новую permission/surface.

## Неизвестные

- Точные account-specific warehouse, delivery point, return point и credential-expiry fields.
- Точные posting-specific marking/exemplar requirements и package-label readiness.
- Конкретные FBO destination/timeslot options и supply-specific GM/TGM rules.
- Нужен ли для конкретного метода Ozon отдельный act/carriage/pass и какие mutations доступны в конкретном external state.
- Ozon-specific condition inspection при возврате.

Все эти неизвестные сохраняют UI без изменений. Если без неизвестного нельзя гарантировать корректную внешнюю операцию, операция заблокирована до отдельно разрешённого read-only evidence. Реальные stock writes даже с тестовым Ozon account запрещены.

## Риски

- Новый control, выведенный только из названия API endpoint, вернёт отвергнутый параллельный workflow.
- Разделение общего FBS maximum на независимые WB/Ozon pools или обход `allocated_elsewhere` создаст oversell.
- Неатомарный cross-marketplace reserve создаст гонку за одну физическую единицу.
- Подмена Ozon provider label внутренним/WB barcode приведёт к ошибке физической приёмки.
- Автоматическое внешнее создание supply до destination/timeslot discovery либо GM/TGM rules создаст некорректное external state.
- Показ локального success до provider confirmation даст оператору ложный статус завершения.
- Расширение seller permissions или seller screens ради stock self-service нарушит подтверждённый actor split и незаметно создаст новый операторский процесс.

## Конкретная передача архитектору

- Использовать этот документ как единственный новый практический S0 owner contract; не восстанавливать требования из старых `ARCH`, `REUSE_MAP`, макетов, прототипов, тестов или run-артефактов.
- Зафиксировать invariant адаптера: provider/account identities меняют данные, conditional copy, print asset и enabled state только в названной existing zone; routes, tables, workspace roots и stage topology не меняются.
- Сохранить точно двухуровневый stock process: один общий catalog `Остаток FBS`, затем per-binding allocation в existing dialog; сумма WB+Ozon allocations ограничена common pool через `allocated_elsewhere`.
- Сохранить actor split без новой permission: seller owner/admin обслуживает только Ozon connection в `/seller/settings`; FF admin владеет common FBS pool, allocations и publication в существующих FF screens. Не проектировать и не добавлять seller self-service stock surface.
- Сохранить atomic reservation из общего available stock для обоих marketplaces и provider-homogeneous external mutations/documents.
- Представить `UNKNOWN` как capability-off/blocker, а не как control placeholder. Для снятия blocker требуется отдельное read-only evidence; real Ozon FBS stock writes с тестовым аккаунтом запрещены.
- Разрешить visible delta только в существующей зоне и только с evidence: provider prefix/copy, conditional Ozon mandatory value в marking row и provider label в print zone.

## Acceptance self-check

- ROOT PRODUCT VALIDATION v3: принято 44/44.
- В документе ровно 44 numbered Q&A entries.
- Каждый ответ содержит `Baseline`, `Решение владельца`, `Official necessity/evidence`.
- `UNKNOWN` не создаёт control: UI unchanged и/или operation blocked.
- Общий двухуровневый FBS pool и per-binding allocation сохранены точно.
- Seller owner/admin ограничен Ozon connection в `/seller/settings`; FF admin явно владеет common FBS pool, allocations и publication; seller self-service stock surface/permission не вводится.
- Production-код, тесты, старые документы, архитектура, прототипы и run-артефакты не являются частью этого контракта и не должны изменяться этим call.
