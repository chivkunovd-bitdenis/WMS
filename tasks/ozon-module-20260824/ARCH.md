# Stage 0. Архитектура модуля Ozon для WMS

**Call ID:** `02-ozon-architecture`
**Основание:** просьба владельца «Сделать модуль Ozon» и принятое исследование `docs/runs/ozon-module-20260824/01-ozon-domain-research.md` на commit `0c3abe3c31ba7b9216401eddd0e15971263eca15`
**Статус:** архитектурное решение до BA/Product/Dev; production-код этим документом не разрешён
**Дата:** 24 августа 2026 года

## 1. Решение в одном абзаце

Модуль строится рядом с действующим Wildberries-контуром, а не путём переименования WB FBS. Общими становятся только безопасные интеграционные механизмы: кабинет маркетплейса, обнаруженные возможности, account-scoped сопоставление товаров, внешние узлы и их связь с физическим складом, checkpoint синхронизации, inbox push-событий, журнал внешних операций, аудит и бинарные документы. Ozon получает собственные агрегаты FBS posting → line → unit/exemplar → package → optional carriage/act и FBO supply order → supply → cargo → transport cargo (ТГМ) → acceptance act. Существующие WB-модели, маршруты, jobs, экраны, печатная лента и publisher остатков не мигрируют и остаются регрессионной границей. Запись FBS-остатков Ozon отсутствует в разрешённых возможностях, клиенте, API, jobs и типах operation ledger, поэтому она невозможна по конструкции, а не только скрыта в интерфейсе.

## 2. Что известно, что решено, что пока неизвестно

### Подтверждено исследованием и кодом

- Для прямого Seller API Ozon нужна пара `Client-Id` + `Api-Key`; имеющийся тестовый маркер содержит только `Api-Key`, поэтому live probe сейчас невозможен.
- Один Ozon FBS posting содержит несколько товарных строк и количества; он может быть разделён на postings/packages.
- Для FBS доступна поштучная сдача по штрихкоду posting; общая carriage нужна не всегда.
- FBO draft/supply, cargo и часть документов являются асинхронными операциями, успех HTTP-запроса не равен успеху бизнес-операции.
- Push может запаздывать, поэтому polling остаётся обязательным механизмом восстановления.
- Текущие WMS `FbsOrder`, `FbsSupply`, `FbsTrbx`, WB credentials, routes, jobs и print flow кодируют WB lifecycle. В частности, `FbsOrder` хранит один `product_id`, а WB stock publisher вызывается из общих событий движения остатка.
- WMS уже имеет пригодные общие части: tenant/seller, `Product`, физический `Warehouse`/ячейки, inventory balance/movement, packaging task, marking pool, background job shell, роли/права, зашифрованное хранение интеграционных секретов и бинарные print assets.

### Архитектурные решения этого документа

- Один seller может одновременно иметь WB и один или несколько Ozon accounts; любой внешний идентификатор всегда scoped через `marketplace_account_id`.
- Каталог Ozon на этом этапе import-only: WMS читает карточки, атрибуты и остатки, но не создаёт и не изменяет карточки.
- FBS stock publishing Ozon не входит в модуль и не существует как выключенный toggle. Его добавление потребует отдельного owner-approved research/product gate и отдельной миграции контракта.
- Ozon mutating operations разрешаются не общей ролью «write», а пересечением трёх условий: возможность подтверждена Ozon, разрешена политикой проекта и доступна в `available_actions` конкретной сущности.
- Внешний lifecycle и внутренний складской workflow хранятся раздельно. Неизвестный внешний status сохраняется raw и переводит сущность в `needs_attention`, но не ломает импорт.
- Возврат сначала попадает в карантинную приёмку WMS; внешнее сообщение о возврате никогда само не увеличивает доступный остаток.

## 3. Primary user и его работа

**Primary user — оператор фулфилмент-склада**, который отвечает не за «синхронизацию API», а за физически правильную единицу товара: увидеть работу к сроку, взять товар из правильной ячейки, просканировать нужные идентификаторы, упаковать допустимым способом, наклеить актуальную этикетку, передать Ozon и затем принять возврат без ложного прихода в доступный остаток.

Заметные элементы будущего процесса привязаны к этой работе:

- Очередь по сроку нужна оператору, чтобы сначала собирать то, что реально рискует опоздать, а не просматривать технические ID.
- Количество строк и единиц показывается отдельно, потому что «2 товара / 5 штук» определяет объём подбора и число экземпляров маркировки.
- Блокеры «не сопоставлен товар», «не связан склад», «не принят КИЗ» стоят рядом с недоступным действием, потому что оператор должен понимать, какую физическую работу нельзя продолжать и кто способен снять блокер.
- Скан ячейки перед сканом товара доказывает, откуда взята единица, и защищает остаток от списания из другой ячейки.
- Package и короб WMS показаны раздельно: оператор физически кладёт товар в короб, но Ozon определяет внешнюю упаковку/posting label; смешение даст неверную этикетку.
- Состояние «передано WMS, Ozon ещё не подтвердил» остаётся видимым, потому что оператору и руководителю смены нужен путь арбитража, а не ложное «готово».
- Возврат открывает осмотр и карантин, потому что сотрудник не может вернуть повреждённую или подменённую единицу в продажу только по внешнему статусу.

Secondary users:

- **Администратор FF** подключает account, проверяет identity/roles/expiry, связывает Ozon товары и склады с WMS. Ему не нужны операционные кнопки упаковки.
- **Планировщик FBO / руководитель смены** выбирает маршрут, таймслот, состав, cargo/ТГМ и разбирает uncertain operations и акты расхождений.
- **Сотрудник приёмки** принимает Ozon returns, идентифицирует исходную единицу и фиксирует результат осмотра.
- **Seller user** получает read-only видимость своих сопоставлений, postings/supplies/returns в рамках `effective_seller_id`; mutating кабинет Ozon из seller portal в первый релиз не переносится.

## 4. Нормальный процесс end to end

### 4.1 Подключение и подготовка общего контура

1. Администратор выбирает WMS seller и создаёт отдельный Ozon account. Если доступна прямая авторизация, вводятся оба значения `Client-Id` и `Api-Key`; если позднее подтверждён private-app OAuth, он создаёт другой credential record того же account, а не подменяет поля прямого ключа.
2. WMS не считает account активным после сохранения секрета. Read-only discovery job вызывает сведения о продавце и ролях, фиксирует внешний account identity, expiry и capabilities. При несовпадении уже зафиксированной identity account блокируется как `identity_mismatch`.
3. WMS импортирует товары, склады продавца, Ozon warehouses, delivery methods, clusters/placement zones и return points только теми read endpoints, которые доступны account. Каждая ресурсная синхронизация имеет свой checkpoint.
4. Администратор связывает Ozon offer/product/SKU с WMS Product. Автопредложение по точному уникальному barcode или seller SKU разрешено, но превращается в active mapping только после явного подтверждения; неоднозначный матч остаётся `conflict`.
5. Администратор связывает физический WMS warehouse с внешними узлами отдельно для FBS и FBO. На экране видны разные сущности: физический склад, seller warehouse, destination/cluster, delivery method и return point. Одно поле «склад маркетплейса» их не заменяет.
6. После первой полной синхронизации account становится `active_read_only`. Каждая mutating capability включается только если прошла discovery, разрешена project allowlist и проверена contract fixture. Отсутствующая возможность не блокирует весь модуль: связанное действие показывается как manual/external fallback.

### 4.2 Ozon FBS: от posting до возврата

1. Push-событие ускоряет получение нового posting, но poll `/v4/posting/fbs/unfulfilled/list` гарантирует восстановление. Inbox дедуплицирует события, после чего detail readback создаёт или обновляет posting, строки и требования экземпляров.
2. WMS проверяет account, mapping каждой строки и warehouse binding. Только затем резервирует количество по каждой line в выбранном физическом складе. Posting с двумя строками создаёт два резерва; shortage одной строки не скрывает готовность другой.
3. Оператор открывает очередь Ozon FBS, видит срок, seller, маршрут сдачи, число строк/единиц и единственный следующий шаг. Он может собрать локальную рабочую партию для маршрута по ячейкам, но это не создаёт внешнюю Ozon carriage.
4. В подборе оператор сканирует ячейку, затем товар. Каждая принятая единица фиксирует location, product, posting line, пользователя и время. Лишний скан, скан другого seller или другой line отклоняется до изменения количества.
5. Если posting требует код маркировки, IMEI, GTIN, вес или страну происхождения, экран запрашивает только реально требуемые поля конкретной единицы. Локальный scan и внешний exemplar validation — два статуса. Ошибка Ozon оставляет единицу исправляемой до упаковки.
6. PackagingTask остаётся authority физической упаковки: его line/events фиксируют работу с остатком. Ozon bridge связывает это событие с posting line/unit/package. Package composition хранит количества, поэтому partial package не превращает всю line в packed.
7. Перед внешним ship WMS делает fresh detail/restrictions readback, проверяет `available_actions`, accepted exemplars, габариты/вес и package composition. Создаётся operation intent; бизнес-статус не меняется на `awaiting_deliver`, пока readback не подтвердит результат.
8. После подтверждённого ship запускается асинхронная задача package label. Оператор печатает только `ready` asset актуальной версии. Старый asset помечен superseded и недоступен как основной.
9. Handover выбирается по capability и delivery method:
   - при one-by-one оператор сдаёт каждый posting по его barcode; WMS фиксирует ручное подтверждение передачи, затем ждёт внешний status;
   - при carriage postings группируются только после проверки совместимости; approve/act/pass выполняются отдельными operations;
   - если API-действие отсутствует, WMS показывает пошаговое ручное действие в кабинете Ozon и после него делает readback, не ставя внешний статус вручную.
10. Состояния `handed_over_wms`, `delivering`, `delivered` и arbitration хранятся отдельно. Если Ozon не подтвердил скан, руководитель смены открывает recovery, прикладывает доступный act/discrepancy asset и ведёт арбитраж; обычный оператор не может нажать «доставлено».
11. Отмена до подбора освобождает резерв. Отмена после подбора создаёт reverse work item: единицы возвращаются в подтверждённую ячейку или карантин, и только проведённое inventory movement освобождает физический остаток.
12. `/v1/returns/list` создаёт отдельный return aggregate, связанный с posting/line/unit. При фактическом получении WMS создаёт `InboundIntakeRequest(operation_type=return)` в карантин. После осмотра сотрудник выбирает restock, quarantine, defect или return-to-seller; только проведённая приёмка меняет остаток.

### 4.3 Ozon FBO: от плана до возврата

1. Планировщик создаёт локальный FBO plan из WMS Products и количеств, выбирает физический склад-источник и один из обнаруженных вариантов direct/crossdock/multi-cluster. Недоступные варианты не показываются как активные.
2. WMS читает clusters, destination nodes, placement zones и правила маршрута. Планировщик видит не технические справочники, а место сдачи, ожидаемый маршрут и ограничения, влияющие на физическую подготовку груза.
3. Draft create создаёт operation ledger entry. `operation_id` сохраняется, status poll подтверждает результат. При timeout WMS сначала читает status/draft, а не создаёт второй draft.
4. Планировщик выбирает предложенный таймслот. Создание supply order также проходит через async operation и readback. Локальный plan и внешний supply order остаются разными сущностями.
5. После появления supply order WMS фиксирует supplies и состав. Любое изменение состава или таймслота создаёт новую operation revision; предыдущая версия остаётся в аудите.
6. Для физической подготовки создаётся PackagingTask и резерв/подбор из WMS warehouse. Оператор видит по каждой line planned, picked, packed и externally accepted quantities. Требуемые данные товара берутся из Ozon response; неизвестное обязательное поле блокирует submit, но не теряется в raw snapshot.
7. WMS читает cargo rules. Оператор создаёт WMS boxes, затем явно связывает их с Ozon cargo. Транспортные грузоместа (ТГМ) образуют следующий уровень и могут содержать несколько cargo. Нельзя автоматически считать WMS box cargo или ТГМ.
8. Cargo create/delete и label generation являются async operations. После readback оператор печатает актуальные cargo/TGM labels и отмечает фактическое нанесение. Ошибка одной cargo остаётся частичным состоянием, не откатывая уже подтверждённые cargo.
9. Перед сдачей preflight проверяет подтверждённый supply order, актуальный timeslot, полный состав, cargo rules, нанесённые labels и разрешённое внешнее действие. WMS фиксирует физическую передачу отдельно от внешней доставки.
10. Poll/push ведёт supply lifecycle и FBO postings. `Отгружено WMS`, `доставлено Ozon`, `принято Ozon`, `остаток появился` и `акт согласован` не схлопываются в один статус.
11. Acceptance act импортируется построчно. Расхождение planned/accepted/rejected требует решения руководителя смены. Если capability beta-act accept доступна, принятие акта идёт через ledger и status readback; иначе WMS показывает ручную работу в кабинете и продолжает read-only reconcile.
12. FBO return импортируется тем же return aggregate, но хранит scheme=`fbo` и links на supply/posting/act line. Физическая приёмка и disposition совпадают с безопасным WMS return flow: quarantine по умолчанию, отсутствие автоматического restock.

## 5. Ошибки, частичные состояния и восстановление

| Ситуация | Что видит пользователь и почему | Машинное состояние | Восстановление |
|---|---|---|---|
| Нет `Client-Id` или только один credential | «Подключение не проверено; запросы в Ozon не выполнялись», чтобы администратор не принял наличие ключа за работающий кабинет | account `pending_credentials` | добавить полную пару или OAuth; затем discovery |
| Identity/role/expiry изменились | Account banner и точная недоступная возможность, чтобы оператор не начал необратимую работу | `degraded` / `identity_mismatch` / `expired`; capabilities invalidated | admin reconnect; read-only data остаются видимыми как stale |
| 429 или временная сеть | Последние успешные данные с временем и «повтор запланирован», чтобы очередь не становилась пустой | job `retry_scheduled`, checkpoint не продвинут | respect retry headers, jittered backoff, тот же page/intent |
| Sync оборвался после части страниц | Строки помечены «обновлено частично», а не удаляются | run `partial`; checkpoint на последней committed page | повтор с того же cursor/window; tombstone только после полного прохода |
| Push duplicate/out-of-order | Пользователь не видит двойных заказов и отката статуса | inbox duplicate/obsolete | detail readback является authority |
| Product/warehouse не сопоставлен | Posting видим в блокерах без кнопки подбора, потому что физический товар/склад неизвестен | `blocked_mapping` / `blocked_binding` | admin link; затем deterministic re-evaluation/reserve |
| Нехватка одной FBS line | Готовые строки видны отдельно, но ship заблокирован, чтобы не потерять дефицит | line `shortage`, posting `partial_ready` | пополнение, разрешённый split/partial package либо ручное решение |
| Ozon отменил до/после pick | До pick резерв снимается; после pick появляется возврат в ячейку | `cancelled_unpicked` / `reverse_required` | scan destination, compensating inventory movement, audit |
| Exemplar rejected | На конкретной единице код и Ozon error, потому что заменять весь posting не нужно | exemplar `rejected` | исправить/заменить до package freeze, validate повторно через новый intent |
| Mutation timeout | Никакого «успешно» и активной кнопки повторить, чтобы не создать дубль | operation `uncertain` | обязательный readback; `confirmed`, `rejected` или shift-lead recovery |
| Label task pending/failed | Упаковка сохранена, печать заблокирована только для неготового asset | asset `requesting` / `error` | poll task; safe new request лишь после readback предыдущей задачи |
| Частично созданы FBO cargo | Подтверждённые cargo остаются, ошибочная строка подсвечена отдельно | cargo per-row state + operation failure | исправить только rejected cargo; не пересоздавать всё |
| Ozon не подтвердил handover | «Передано складом, Ozon не подтвердил», чтобы не терять арбитраж | `handed_over_wms` + external unchanged | poll/readback, act/discrepancy, shift-lead escalation |
| Return не сопоставлен | Приёмка разрешена только в quarantine, чтобы не потерять физический товар | return `unmatched`, inbound `return` | scan barcode, ручная связь с product/account, inspection |
| Неизвестный status/field | Raw значение показывается в «Требует внимания», но импорт продолжается | `needs_attention`, raw snapshot retained | обновить adapter contract отдельным slice; оператор использует manual fallback |

## 6. Граница ответственности

### WMS отвечает за

- tenant/seller/account scope и разграничение пользователей;
- физический WMS warehouse, ячейки, доступный остаток, резерв, подбор, упаковку и компенсирующие движения;
- подтверждённые человеком scans, нанесение этикетки и факт физической передачи;
- product mapping и warehouse/delivery binding;
- job/checkpoint/inbox/operation ledger, readback-before-retry и аудит;
- хранение версионированных документов и связь возврата с карантинной приёмкой;
- нормализованный операторский workflow, но не за объявление внешнего статуса без Ozon.

### Ozon отвечает за

- external account identity, roles, expiry и фактические capabilities;
- offer/product/SKU, seller/Ozon warehouses, delivery methods, clusters, placement zones и return points;
- posting/supply/cargo lifecycle, `available_actions`, restrictions, async task result;
- package/cargo/TGM labels, acts, pass/giveout documents и внешнюю приёмку;
- внешний FBS/FBO stock snapshot. WMS его читает, но в этой архитектуре не публикует FBS stock.

### Ручные действия остаются ручными

- ввод/обновление credentials уполномоченным администратором;
- подтверждение предложенного product mapping и warehouse binding;
- scan ячейки, товара, экземпляра, коробки/cargo/ТГМ;
- физическая упаковка, печать и нанесение этикетки;
- передача в пункт/водителю и получение возврата;
- осмотр возврата и disposition;
- работа в Ozon seller portal, когда capability/API contract не подтверждён;
- решение руководителя смены по uncertain operation, расхождению акта или арбитражу.

## 7. Варианты архитектуры и цена

Оценки ниже — относительная цена реализации одним устойчивым потоком разработки после утверждённого прототипа, а не календарное обещание.

| Вариант | Суть | Цена реализации и миграции | Эксплуатационная цена | Вердикт |
|---|---|---|---|---|
| 1. Полностью отдельный Ozon silo | Скопировать auth/catalog/jobs/печать и создать только `ozon_*` контур | 11–15 инженерных недель; миграция WB отсутствует | Быстрый первый экран, но дублируются credentials, checkpoint, ledger, documents и permissions; третья площадка снова копирует всё | Не выбран: локально дешевле, системно дороже и увеличивает риск разных правил recovery |
| 2. Малое marketplace integration core + Ozon-native lifecycles | Общие только account/mapping/nodes/sync/ledger/audit/assets/returns; FBS/FBO остаются Ozon-specific; WB не мигрирует | 16–21 инженерная неделя, включая emulator, contract fixtures и browser gates; additive migrations, без data rewrite WB | Новая площадка переиспользует безопасный каркас, но проходит свой domain research; Ozon и WB не притворяются одинаковыми | **Выбран**: минимизирует WB regression и одновременно не создаёт второй набор критической интеграционной инфраструктуры |
| 3. Полная универсализация и миграция WB | Перевести WB и Ozon на один order/supply/package lifecycle | 28–40+ инженерных недель и сложная online data migration/dual-write | Самый высокий риск остановить работающий FBS; универсальная модель либо разрастается union-полями, либо теряет специфику | Отклонён: цена и риск не оправданы, совместимость не доказана |

### Почему выбран вариант 2

Пользовательская работа совпадает у площадок только в физическом ядре — найти, взять, упаковать и передать товар. Внешняя форма работы различается: WB order/supply/trbx против Ozon posting/line/package/optional carriage и FBO cargo/TGM. Поэтому выбранный seam заканчивается до lifecycle. Это позволяет одному seller безопасно видеть WB и Ozon одновременно, но не заставляет Ozon проходить через WB supply workspace и не подвергает WB data migration до отдельного доказательства.

## 8. Целевая структура модулей

```text
WMS core (существует)
  Tenant -> Seller -> Product
  Warehouse -> StorageLocation -> InventoryBalance/Movement
  PackagingTask / MarkingCode / User permissions

Marketplace integration core (новый, additive)
  MarketplaceAccount -> Credential -> CapabilitySnapshot
  ExternalProduct -> ProductMappingHistory
  ExternalNode -> WarehouseDeliveryBinding
  SyncRun/Checkpoint + PushInbox
  MarketplaceOperation -> Attempts/Readbacks
  MarketplaceDocumentAsset + AuditEvent
  MarketplaceReturn -> Lines/Units -> InboundIntake(return)

Ozon adapter and native aggregates (новые)
  Ozon FBS Posting -> Lines -> UnitExemplars -> Packages -> PackageLines
                   -> optional Handover/Carriage -> Acts
  Ozon FBO Plan -> SupplyOrder -> Supplies -> Lines
                -> Cargo -> CargoLines -> TransportCargo(TGM)
                -> TimeslotHistory -> AcceptanceAct/Lines

WB boundary (без миграции)
  SellerWildberriesCredentials / imported cards & supplies
  FbsOrder / FbsSupply / FbsTrbx / FbsPrintAsset / FbsWbOperation
  wildberries routes, clients, jobs, screens, stock publisher and tests
```

Папки backend следуют существующему контракту: routes в `backend/app/api`, orchestration/business rules в `backend/app/services`, models в `backend/app/models`, Celery entrypoints в `backend/app/tasks`. Внешний Ozon transport находится в services adapter, но не импортируется из inventory services.

## 9. Данные и миграции

Во всех новых таблицах есть UUID `id`, `tenant_id`, timestamps и индексы tenant/account/state. Все ссылки на account дополнительно проверяются сервисом на тот же tenant и seller; знание UUID не даёт cross-tenant access.

### 9.1 Shared marketplace integration core

| Таблица | Ключевые поля и ограничения | Семантика |
|---|---|---|
| `marketplace_accounts` | `tenant_id`, `seller_id`, `marketplace`; `external_account_key` nullable до discovery; `auth_mode`; `display_name`; `status`; `identity_fingerprint`; `last_discovered_at`; unique `(marketplace, external_account_key)` только для non-null, плюс unique active direct account `(seller_id, marketplace, external_account_key)` | Один конкретный кабинет. WB credentials пока не переносятся сюда; coexistence достигается независимыми строками Ozon рядом с WB legacy |
| `marketplace_account_credentials` | PK/FK `account_id`; encrypted `client_id`, `api_key`, `oauth_access`, `oauth_refresh`; `expires_at`; `credential_version`; никаких plaintext response fields | Секреты читаются только adapter job. API отдаёт booleans, auth mode, expiry и last check |
| `marketplace_capability_snapshots` | `account_id`, `revision`, `roles_json`, `raw_json_sanitized`, `observed_at`, `valid_until`; unique `(account_id, revision)` | Не перезаписываем историю ролей/expiry |
| `marketplace_capabilities` | `snapshot_id`, `capability_key`, `observed_state`, `project_policy`, `reason`; unique `(snapshot_id, capability_key)` | Effective capability = observed allowed ∧ project allowlist ∧ entity action. `ozon.fbs.stock.write` не является допустимым key этой версии |
| `marketplace_external_products` | `account_id`, `offer_id`, `product_id_external`, `sku_external`, name, barcodes JSON, attributes/requirements/stock snapshots, raw sanitized, `observed_at`, `missing_since`; unique account-scoped external identifiers | Импортированный внешний товар, не WMS Product |
| `marketplace_product_mappings` | `account_id`, `external_product_id`, `product_id`, `status`, `match_method`, `valid_from/to`, `confirmed_by_user_id`, `replaced_by_id`; partial unique active `(account_id, external_product_id)` | История link/unlink; один Ozon SKU разных accounts не смешивается |
| `marketplace_external_nodes` | `account_id`, `scheme`, `kind`, `external_id`, `parent_id`, name, raw sanitized, `active`, `observed_at`; unique `(account_id, kind, external_id)` | seller warehouse, Ozon warehouse, cluster, placement zone, delivery method, return point — разные kinds |
| `marketplace_warehouse_bindings` | `account_id`, `scheme`, `wms_warehouse_id`, `seller_warehouse_node_id`, `destination_node_id`, `delivery_method_node_id`, `return_point_node_id`, `status`, `valid_from/to`; no stock-sync flag | Физическая топология. Для Ozon write policy всегда read-only и не настраивается |
| `marketplace_sync_runs` | account/resource/version/filter hash, started/finished, status, page/item counters, error class/code | Видимый полный/partial результат одного запуска |
| `marketplace_sync_checkpoints` | unique `(account_id, resource, api_version, filter_fingerprint)`; `cursor_kind`, `cursor_json`, `window_from/to`, `generation`, `last_success_at`, `resume_after`, `state` | Checkpoint формы не унифицируются до `page=1`; cursor JSON интерпретирует adapter resource |
| `marketplace_push_inbox` | `account_id`, `event_type`, `external_event_id` nullable, `dedupe_hash`, external occurred/received time, sanitized payload, status; unique `(account_id, dedupe_hash)` | Push — hint. Business aggregate меняется после detail readback |
| `marketplace_operations` | `account_id`, `operation_kind`, local/external entity refs, `intent_fingerprint`, `capability_snapshot_id`, `state`, external task/operation ID, request/response sanitized summaries, last readback, next attempt, error class/code, `supersedes_id`, actor; partial unique active `(account_id, operation_kind, intent_fingerprint)` | Единственный журнал mutating intents; stock write kind отсутствует |
| `marketplace_operation_attempts` | operation, sequence, dispatched/finished, outcome, HTTP class/status, retry headers sanitized, request hash, response hash, readback flag | Неизменяемая история попыток без секретов и маркировочных кодов в открытом виде |
| `marketplace_audit_events` | actor, account, entity, action, before/after hashes, reason, request correlation, occurred_at | Админские связи, operator scans, overrides, print/applied, recovery и disposition |
| `marketplace_document_assets` | account, entity type/id, kind, status, source system/API/version/task, storage path, content type, checksum, dimensions, external/version time, expiry, supersedes, opened/printed/applied by/time, error | Общая безопасная оболочка; WB `FbsPrintAsset` остаётся без миграции |

### 9.2 Ozon FBS data

| Таблица | Ключевые поля |
|---|---|
| `ozon_fbs_postings` | `account_id`, `posting_number`, scheme=`fbs`, external `status/substatus/available_actions/raw`, delivery method/node refs, deadlines, `workflow_state`, `snapshot_version`, cancellation/arbitration JSON; unique `(account_id, posting_number)` |
| `ozon_fbs_posting_lines` | posting, stable external line fingerprint, external product, mapped WMS product nullable, offer/sku, quantity ordered/reserved/picked/packed/handed_over/returned, requirements JSON, workflow state; unique `(posting_id, external_line_fingerprint)` |
| `ozon_fbs_unit_exemplars` | line, ordinal, WMS marking_code nullable, kinds/values encrypted or hashed+masked according to compliance, local scan state, external set/validation state and errors, frozen_at; unique `(line_id, ordinal)` and unique active normalized code hash per tenant/kind |
| `ozon_fbs_reservations` | line, warehouse/location nullable, quantity, state, acquired/released, movement refs; sum(active) ≤ line ordered and no cross-seller Product |
| `ozon_fbs_work_batches` / `_postings` | local warehouse work grouping, route fingerprint, status, creator; membership does not imply Ozon carriage |
| `ozon_fbs_packages` | posting, external package/posting ref, local WMS box nullable, state, restrictions snapshot/version, dimensions/weight, ship operation ref; unique active external ref account-scoped |
| `ozon_fbs_package_lines` | package, posting line, quantity; sum(package quantity per line) ≤ picked quantity |
| `ozon_fbs_packaging_fulfillments` | posting line/unit/package, PackagingTask/line/event, inventory movement, idempotency key, undone_at | Bridge reuses physical packaging without forcing Ozon into `FbsOrder` |
| `ozon_fbs_handovers` | account, mode `one_by_one|carriage|manual_external`, delivery binding, state, external carriage ID nullable, physical confirmed actor/time, external confirmed time |
| `ozon_fbs_handover_postings` | handover, posting, barcode asset, external state; a posting has at most one active handover |
| `ozon_fbs_acts` | handover/posting scope, act kind/status, create operation, document asset, discrepancy state |

### 9.3 Ozon FBO data

| Таблица | Ключевые поля |
|---|---|
| `ozon_fbo_plans` | account, WMS source warehouse, mode `direct|crossdock|multi_cluster`, destination/cluster/placement refs, workflow state, active revision, creator |
| `ozon_fbo_plan_lines` | plan, external product/mapping, WMS product, planned/picked/packed quantity, required data snapshot; unique `(plan, external_product)` |
| `ozon_fbo_supply_orders` | plan, external supply order ID, external lifecycle/raw, local state, current timeslot and version; unique `(account_id, external_supply_order_id)` |
| `ozon_fbo_supplies` / `_lines` | supply order, external supply ID; per-line planned/current/accepted/rejected quantities and raw requirements |
| `ozon_fbo_timeslot_events` | supply order, proposal/selected interval, timezone, source revision, operation, status; immutable history |
| `ozon_fbo_cargoes` | supply, external cargo ID nullable, cargo type, local WMS box/pallet nullable, state, rule snapshot/version, operation refs |
| `ozon_fbo_cargo_lines` | cargo, supply line, quantity; sum cannot exceed packed quantity |
| `ozon_fbo_transport_cargoes` | supply, external TGM ID/type, parent transport nullable, state, label asset |
| `ozon_fbo_transport_cargo_members` | TGM, cargo; unique active cargo membership |
| `ozon_fbo_acceptance_acts` / `_lines` | supply order, external act ID/version/status, operation/document; product line planned/accepted/rejected/reason |

### 9.4 Returns data

`marketplace_returns` хранит account, scheme `fbs|fbo`, external return ID, source posting/supply refs, location/giveout/pass refs, external lifecycle/raw, workflow `announced|ready_for_pickup|received_quarantine|inspecting|disposed|closed|needs_attention`, linked `inbound_intake_request_id`. `marketplace_return_lines` хранит external product, mapped product, expected/received quantity и reason. `marketplace_return_units` связывает исходный exemplar/barcode, inspection outcome и disposition. `marketplace_return_events` — неизменяемая история. Unique `(account_id, external_return_id)` не даёт смешать возвраты двух кабинетов.

### 9.5 Порядок additive migrations

1. **M1 integration foundation:** accounts, encrypted credentials, capability snapshots/entries, audit; seed отсутствует, WB rows не трогаются.
2. **M2 import topology:** external products, mapping history, external nodes, bindings, indexes/tenant checks.
3. **M3 reliability spine:** sync runs/checkpoints, push inbox, operations/attempts, document assets.
4. **M4 Ozon FBS read model:** postings/lines/units/reservations/work batches; imports включаются feature flag только после backfill test.
5. **M5 Ozon FBS execution:** packages/package lines/packaging bridge/handovers/acts.
6. **M6 Ozon FBO:** plans/lines/supply orders/supplies/timeslots/cargo/TGM/acts.
7. **M7 returns:** returns/lines/units/events и nullable link на существующую inbound return.
8. **M8 UI availability flags only if needed:** per-tenant/account rollout flags. Existing permission columns do not migrate: settings/admin, packaging, mp_shipments, reception and shift_lead are reused.

Каждая migration обязана пройти upgrade на копии схемы, downgrade там, где он не уничтожает уже созданные внешние факты, и schema-from-zero. Удаление/перенос WB колонок запрещено этой серией.

## 10. API WMS

Внешний Ozon endpoint/version живёт только внутри adapter operation matrix. Frontend вызывает стабильные WMS routes и не знает `v4/v6` Ozon.

### 10.1 Зафиксированная граница Ozon adapter

Ниже перечислены подтверждённые research dossier operation families. Перед реализацией соответствующего slice точная request/response schema замораживается sanitized fixture и датой; путь, помеченный beta/уточнением, не включается одной догадкой.

| Ресурс | Ozon paths | Режим в WMS |
|---|---|---|
| Account | `/v1/seller/info`, `/v1/roles` | Только read discovery; identity/roles/expiry |
| Products | `/v3/product/list`, `/v3/product/info/list`, `/v4/product/info/attributes`, `/v4/product/info/stocks` | Import-only; unknown fields retained |
| Stock snapshots | `/v2/product/info/stocks-by-warehouse/fbs`, `/v1/product/info/stocks-by-warehouse/fbo`, `/v1/analytics/stocks` | Read-only observation. `/v2/products/stocks` отсутствует в adapter |
| Product requirements | `/v1/description-category/*` | Read attributes, включая 22232 ТН ВЭД и 23536 «нужен код маркировки»; no product write |
| Nodes/routes | `/v2/warehouse/list`, `/v2/delivery-method/list`, `/v2/carriage/delivery/list`, `/v1/warehouse/ozon/list` beta, `/v1/warehouse/fbo/seller/list`, `/v2/cluster/list` | Read topology and capability-dependent options |
| Invalid FBS products | `/v1/warehouse/warehouses-with-invalid-products`, `/v1/warehouse/invalid-products/get` | Read blockers before reserve/ship |
| FBS postings | `/v4/posting/fbs/unfulfilled/list`, `/v4/posting/fbs/list`, `/v3/posting/fbs/get` | Poll/list/detail authority; no deprecated v3 list |
| FBS package rules | `/v1/posting/fbs/restrictions` | Fresh read in ship preflight |
| FBS unit exemplars | `/v6/fbs/posting/product/exemplar/create-or-get`, `/v6/fbs/posting/product/exemplar/set`, `/v5/fbs/posting/product/exemplar/validate`, `/v5/fbs/posting/product/exemplar/status`, `/v1/fbs/posting/product/exemplar/update` | Granular mutating capabilities; ledger + validation readback; old v4/v5 create/set not used |
| FBS split/ship | `/v1/posting/fbs/split`, `/v4/posting/fbs/ship`, `/v4/posting/fbs/ship/package` | Separate capability and intent kinds; allowed only by entity action/preflight |
| FBS labels | `/v2/posting/fbs/package-label/create`, `/v1/posting/fbs/package-label/get` | Async asset task. Older binary path is not assumed without a frozen schema |
| FBS carriage/acts | Confirmed carriage create/get/assign/approve/cancel/pass family, `/v2/posting/fbs/act/create`, `/check-status`, `/get-pdf`, `/get-postings`, `/v1/carriage/act-discrepancy/pdf` | Exact carriage paths/schemas frozen in S6; optional, never parent of every posting |
| FBO draft | `/v1/draft/crossdock/create`, `/v1/draft/direct/create`, `/v1/draft/multi-cluster/create`, `/v2/draft/create/info`, `/v2/draft/timeslot/info` | Capability-dependent async draft and timeslot |
| FBO supply order | `/v2/draft/supply/create`, `/v2/draft/supply/create/status`, `/v3/supply-order/list`, `/v3/supply-order/get` | Ledger task + list/get readback; old v1 draft status family not used |
| FBO cargo | `/v1/cargoes/rules/get`, `/v1/cargoes/get`, `/v1/cargoes/create`, `/v2/cargoes/create/info` and confirmed delete/status family | Rules before mutation, per-cargo partial state. `delete_current_version` value explicit in intent |
| FBO labels | Confirmed cargo-label create/get/file family; exact active versions and binary contract require S8 schema freeze | Capability remains off until fixture/print sample exists |
| FBO postings | `/v3/posting/fbo/list`, `/v2/posting/fbo/get` | Read reconciliation; deprecated v2 list not used |
| FBO acts | `/v1/supply-order/act/summary/get`, `/product/get`, `/accept`, `/accept/status` beta | Read always when available; accept separately gated and status-polled |
| Returns | `/v1/returns/list`, `/v1/returns/company/fbs/info`, confirmed giveout barcode/PDF and pass family `/v1/return/pass/create|update|delete`, `/v1/pass/list` | Unified import; mutating pass/giveout only after exact schema/capability freeze |
| Notifications | `/v1/notification/set|update|check|delete|enable|list|push-type/list` | Poll fallback is default; configuration write is a separate capability after ingress-auth contract is proven |

Для каждой строки adapter хранит operation name, exact path/version, read/mutation class, required effective capability, pagination codec, timeout, retry/readback rule, sanitizer and fixture checksum. Дрейф path не меняет WMS API и не разрешает automatic fallback на старую версию.

### 10.2 Accounts, discovery, catalog and bindings

- `POST /integrations/ozon/accounts` — admin создаёт account shell для seller; credential values не возвращаются.
- `GET /integrations/ozon/accounts?seller_id=` и `GET /accounts/{id}` — masked health, identity, expiry, latest capability snapshot.
- `PUT /integrations/ozon/accounts/{id}/credentials` — admin заменяет полную direct pair или OAuth bundle; только отдельный явно разрешённый product slice.
- `POST /integrations/ozon/accounts/{id}/discover` — read-only BackgroundJob; incomplete pair → `409 incomplete_credentials`, без сетевого вызова.
- `POST /integrations/ozon/accounts/{id}/disable` — прекращает jobs/mutations, не удаляет audit/data.
- `POST /integrations/ozon/accounts/{id}/sync/{resource}` — admin/manual sync для allowlisted `products|nodes|fbs_postings|fbo_supply_orders|returns`; возвращает job ID.
- `GET /integrations/ozon/accounts/{id}/external-products`, `GET /external-nodes` — paginated local read models.
- `PUT /integrations/ozon/accounts/{id}/product-mappings/{external_product_id}` и `DELETE .../active` — admin confirm/unlink with reason.
- `PUT /integrations/ozon/accounts/{id}/warehouse-bindings/{scheme}` — admin creates versioned binding; request names each node kind separately.
- `GET /operations/background-jobs/{job_id}` может быть переиспользован после добавления account-scope authorization; payload никогда не раскрывает secrets/raw marking codes.

### 10.3 FBS routes

- `GET /operations/ozon/fbs/postings` — filters account/seller, warehouse, workflow, deadline, blocker; cursor pagination.
- `GET /operations/ozon/fbs/postings/{id}` — lines, units, packages, blockers, documents, external/local states and `next_action`.
- `POST /operations/ozon/fbs/work-batches` и `POST /{batch_id}/postings` — local grouping only.
- `POST /operations/ozon/fbs/postings/{id}/reserve|release` — internal inventory transaction; release after pick requires reversal path.
- `POST /operations/ozon/fbs/postings/{id}/pick/scan-location` and `/pick/scan-product` — stable scan contract, idempotency key.
- `PUT /operations/ozon/fbs/units/{unit_id}/identifiers` — local scan/update before freeze; values masked in response.
- `POST /operations/ozon/fbs/units/{unit_id}/validate` — ledger-backed Ozon exemplar operation.
- `POST /operations/ozon/fbs/postings/{id}/packages` and `PUT /packages/{id}/lines` — local composition with quantity invariants.
- `POST /operations/ozon/fbs/postings/{id}/ship-preflight` — fresh readback/restrictions; no mutation.
- `POST /operations/ozon/fbs/postings/{id}/ship` — creates operation intent, returns `202 operation_id`.
- `POST /operations/ozon/fbs/packages/{id}/label` and `GET /documents/{asset_id}/content` — async request/read ready asset.
- `POST /operations/ozon/fbs/handovers` — mode chosen from effective capability; postings validated server-side.
- `POST /operations/ozon/fbs/handovers/{id}/physical-confirmation` — records manual fact, not external delivery.
- `POST /operations/ozon/fbs/handovers/{id}/submit|approve|act` — separate intents only when supported.
- `POST /operations/ozon/fbs/postings/{id}/reconcile` and `/reverse-pick` — recovery actions with reason and permission.

### 10.4 FBO routes

- `GET/POST /operations/ozon/fbo/plans`, `GET/PATCH /plans/{id}` — local draft and composition revision.
- `POST /plans/{id}/draft-preflight`, `/draft`, `/timeslot` and `/supply-order` — one preflight and one ledger intent per external async stage.
- `GET /operations/ozon/fbo/supply-orders` and `GET /supply-orders/{id}` — local read model with supply/line/timeslot/cargo/act details.
- `POST /supply-orders/{id}/packaging-task` — creates/reuses PackagingTask after confirmed composition.
- `POST /supply-orders/{id}/cargo-preflight`, `POST/PUT/DELETE /cargoes`, `POST /cargoes/{id}/label` — rules snapshot required.
- `POST/PUT /supply-orders/{id}/transport-cargoes` and membership routes — explicit TGM layer.
- `POST /supply-orders/{id}/handover-preflight` and `/physical-confirmation` — separate local facts.
- `POST /supply-orders/{id}/reconcile` — reads external lifecycle, FBO postings and stock snapshots.
- `GET /supply-orders/{id}/acceptance-act`; `POST /acceptance-act/accept` — latter only with effective beta capability and ledger readback.

### 10.5 Returns, operations and recovery

- `GET /operations/marketplace-returns?marketplace=ozon&scheme=` and `GET /{id}` — shared read view.
- `POST /operations/marketplace-returns/{id}/receive` — creates/links quarantine inbound return, never increments inventory directly.
- `POST /{id}/inspect` and `/dispose` — reception/shift-lead actions with unit outcomes; existing inbound posting remains inventory authority.
- `GET /integrations/marketplace-operations?account_id=&state=` and `GET /{id}` — admin/shift-lead recovery queue.
- `POST /integrations/marketplace-operations/{id}/readback` — always safe read operation.
- `POST /{id}/resolve` with `confirmed|no_effect|abandon|supersede` — shift-lead/admin, mandatory reason; retry is a new linked operation, never mutation of history.

All mutating routes require `Idempotency-Key`; server computes its own canonical intent fingerprint and rejects key reuse with a different payload (`409 idempotency_conflict`).

## 11. Jobs, sync, limits and reconciliation

### Job types

- `ozon_capability_discovery_account`
- `ozon_products_sync_account`
- `ozon_nodes_sync_account`
- `ozon_fbs_unfulfilled_poll_account`
- `ozon_fbs_detail_reconcile_account`
- `ozon_fbo_supply_orders_sync_account`
- `ozon_fbo_postings_sync_account`
- `ozon_returns_sync_account`
- `ozon_operation_status_poll`
- `ozon_document_status_poll`
- `ozon_push_inbox_drain_account`

Каждый payload содержит `marketplace_account_id` и ожидаемую `credential_version`; job прекращается до вызова Ozon, если account disabled, tenant mismatch или credentials сменились. Celery используется при наличии broker, существующий FastAPI `BackgroundTasks` — для локальной разработки/тестов. Periodic jobs выбирают только active accounts и берут per-account/resource lock.

### Default cadence, не внешняя гарантия

- FBS unfulfilled: каждые 2 минуты; active detail: каждые 5 минут; full bounded backfill: каждые 6 часов.
- FBO supply orders/postings: каждые 10 минут; active async operation: 5, 10, 20, 30 секунд, затем adaptive до 5 минут.
- Returns: каждые 15 минут; products/nodes/capabilities: nightly и manual.
- 429 headers имеют приоритет; без них exponential backoff + jitter. Account-wide limiter разделяет budget по endpoint family, write queue не вытесняет order/return reads.

### Checkpoint semantics

1. Adapter задаёт `resource + api_version + filter_fingerprint + cursor_kind`.
2. Страница сохраняется и upsert-ится транзакционно; checkpoint продвигается только в той же committed transaction.
3. `offset`, `cursor`, `last_id`, `has_next`, time window и `operation_id` не приводятся к ложному общему integer page.
4. Удаление внешнего объекта никогда не выводится из одной пропущенной partial sync. `missing_since` ставится после полного прохода; inactive/tombstone — после второго полного прохода либо явного terminal/deleted status.
5. Новый API version создаёт новый checkpoint namespace и backfill; старый остаётся для rollback/audit.

### Push semantics

Receiver не включается, пока не зафиксирован официальный способ проверки подлинности текущей схемы Ozon. Без него fallback — polling. После фиксации схемы endpoint принимает событие в account-specific ingress, проверяет подпись/секрет согласно официальному контракту, сохраняет sanitized payload и быстро отвечает. Даже валидный push не меняет reserve, package, handover или inventory: он ставит detail reconcile. Duplicate определяется external event ID либо canonical payload hash; out-of-order event не откатывает newer external snapshot.

## 12. Operation ledger: точная семантика

Состояния: `created → dispatched → awaiting_external → reconciling → confirmed|rejected`; отдельные `rate_limited`, `uncertain`, `needs_action`, `abandoned`, `superseded`.

Алгоритм mutating action:

1. В одной DB transaction проверить tenant/account, permission, effective capability, fresh external snapshot/`available_actions`, локальные invariants и отсутствие active intent с тем же fingerprint.
2. Создать immutable intent со ссылкой на capability revision и sanitized request summary. Бизнес-сущность получает `operation_pending`, но не внешний success status.
3. Worker перед dispatch ещё раз проверяет account/credential version и записывает attempt. Secrets существуют только в headers transport call и не логируются.
4. При получении external task/operation ID сохранить его до дальнейшего commit и перейти `awaiting_external`.
5. При timeout, connection reset или ambiguous 5xx перейти `uncertain`. Автоматический повтор mutating request запрещён; сначала status/detail readback.
6. Readback подтверждает фактический effect (`confirmed`), явный reject (`rejected`) или отсутствие доказательства (`needs_action`). Только confirmed переводит business aggregate дальше.
7. 429 до доказанного dispatch сохраняет `rate_limited`/`next_attempt_at`; 429 после возможного dispatch считается `uncertain`, если эффект нельзя исключить.
8. Ручной recovery не редактирует operation. Он фиксирует reason и либо закрывает её как no-effect/abandoned, либо создаёт новый intent с `supersedes_id`.

Коды ошибок нормализуются в `auth`, `permission`, `rate_limit`, `validation`, `state_conflict`, `not_available`, `async_failure`, `transport_uncertain`, `unknown`; оригинальные безопасные Ozon code/message остаются в details.

## 13. Права и аудит

Используются существующие права, чтобы не раздувать настройки персонала:

- `FULFILLMENT_ADMIN`: account/credentials/capability discovery, mappings, bindings, sync controls, all recovery.
- `packaging`: FBS queue, reserve/pick/pack/exemplar/label/physical handover; не меняет credentials/bindings и не resolve uncertain mutation.
- `mp_shipments`: FBO plan/composition/cargo/TGM/labels/physical handover.
- `reception`: return receive/inspection; `dispose=restock|defect|seller_return` требует существующих правил проведения приёмки.
- `shift_lead`: irreversible cancel/reversal, act discrepancy, handover arbitration and operation recovery.
- seller `can_products`: read mappings/external catalog своего effective seller; `can_documents`: read postings/supplies/returns/documents; seller mutations Ozon отсутствуют в первом релизе.

Каждый account-scoped query фильтруется server-side по tenant и seller/delegation. Audit обязателен для credential version change (без значений), discovery identity, capability change, mapping/binding version, reserve/release, scans, exemplar correction/freeze, package/cargo membership, print opened/applied, physical handover, operation recovery, act decision и return disposition.

## 14. Print/document taxonomy

Не существует общего `sticker_code`. Виды assets:

- WMS: `product_barcode_label`, `marking_code_label`, `packing_sheet` — источник WMS/Честный знак, не Ozon.
- Ozon FBS: `fbs_package_label`, `fbs_posting_barcode`, `fbs_carriage_barcode`, `fbs_act_pdf`, `fbs_discrepancy_act_pdf`, `return_giveout_barcode`, `return_document_pdf`, `pass_document`.
- Ozon FBO: `fbo_supply_document`, `fbo_cargo_label`, `fbo_tgm_label`, `fbo_pass_document`, `fbo_acceptance_act_pdf`.

Asset обязан знать entity, account, source API/version/task, content type, checksum, dimensions при подтверждении источником, generation time, expiry, version/supersession и факты opened/printed/applied. Формат 58×40 не навязывается Ozon: WMS отдаёт бинарник Ozon в исходном размере либо применяет отдельный утверждённый print transform с visual golden test. Печать старой/superseded версии требует shift-lead override и остаётся в audit.

## 15. Deny-by-construction для Ozon FBS stock write

Запрет доказывается пятью независимыми слоями:

1. В project capability enum/allowlist нет `ozon.fbs.stock.write`; capability discovery может сохранить сырой role, но не превратить его в effective capability.
2. `OzonSellerAdapter` этой версии не имеет метода изменения stocks и не содержит path `/v2/products/stocks`. Product import/update paths также отсутствуют.
3. Нет WMS route, command, BackgroundJob/Celery task или operation kind для Ozon stock write. Warehouse binding не содержит `stock_sync_enabled` и всегда read-only.
4. Общие inventory/catalog services продолжают импортировать только WB `schedule_seller_stock_publish`; они не знают MarketplaceAccount и не могут вызвать Ozon adapter. Существующий `fbs_stock_publish_seller` выбирает только legacy WB credentials/bindings.
5. Outbound test transport для Ozon имеет endpoint allowlist и падает fail-closed на любой неизвестный mutating path. Contract/AST tests проверяют отсутствие stock path, route, job, capability и network call при любом inventory movement.

Отрицательное доказательство в CI:

- create Ozon account с fixture roles, где внешняя роль теоретически шире нужной; effective capabilities всё равно не содержат stock write;
- выполнить inbound, transfer, reserve/release, FBS ship/cancel и FBO operations; recorder Ozon transport должен иметь zero requests к stock-write path;
- попытки создать ledger operation `ozon_fbs_stock_write`, вызвать несуществующий route или передать binding `stock_sync_enabled=true` дают schema/404/422, а не hidden execution;
- source contract check запрещает строку `/v2/products/stocks` вне research docs/negative fixtures.

Будущее включение невозможно одной настройкой или DB row. Потребуются: отдельное owner approval, актуальное Ozon research, новый capability key и migration, adapter method, route/job/ledger kind, UX Product gate, availability formula, sandbox/emulator, readback and rollback design, negative cross-seller tests и новый browser acceptance. До merge всех этих изменений текущая система остаётся физически неспособной публиковать Ozon FBS stock.

## 16. Интеграция frontend без широкого redesign

Добавляется один пункт `Ozon` в существующий `AuthedAppLayout`, видимый администратору либо роли хотя бы с одним из `packaging|mp_shipments|reception`. Он ведёт в scoped module shell `/app/ff/ozon`. Остальная навигация, WB FBS routes, four-column WB table, `WildberriesScreen`, `FfFbsStockSyncScreen` и MP shipment layout не перестраиваются.

Внутри Ozon shell вкладки показываются по работе пользователя:

- `FBS` — оператор packaging;
- `FBO` — planner/operator с mp_shipments;
- `Возвраты` — reception;
- `Каталог и связи` — admin;
- `Подключение` — admin.

Точечные изменения затронутых общих экранов:

- В `FfProductsCatalogScreen` добавить компактный фильтр `Маркетплейс: Все / Wildberries / Ozon / Не сопоставлено`, потому что администратору нужно найти SKU без Ozon mapping. Он не добавляет в основную таблицу все внешние IDs; detail/dialog показывает mappings account-scoped.
- В dashboard добавить Ozon work counts только после delivery slice: «FBS к сборке», «FBO к сдаче», «Возвраты к приёмке». Счётчики ведут в готовую очередь и нужны руководителю смены для распределения людей.
- В существующем разделе «Отгрузки» добавить source badge/filter только для Ozon FBO documents, если выбранная продуктовая карточка интегрирует их туда. До этого Ozon FBO живёт в module shell; WB rows/columns не меняются.
- WB FBS «Остатки WB» остаются WB-only. Ozon stock toggle, вкладка или кнопка не создаются.

## 17. Точное задание на кликабельный React-прототип

### Граница прототипа

Создать отдельный prototype route set в существующем React/MUI приложении без production API, models, migrations и без изменения действующих WB screens. Использовать theme, `PageHeader`, `Paper variant="outlined"`, `Table`, `Tabs`, `TextField`, `Select`, `Alert`, `Dialog`, `Stepper`, `Button`, `LinearProgress`, `Skeleton`; не использовать legacy `frontend/src/ui`. Все основные зоны и действия получают стабильные `data-testid`. Fixtures локальные и детерминированные; prototype actions меняют только in-memory fixture state.

Файловая граница задания: новые компоненты и fixtures живут только в `frontend/src/prototypes/ozon/**`; допускаются две малые интеграционные правки — регистрация prototype routes в `frontend/src/App.tsx` и один nav item в `frontend/src/layouts/AuthedAppLayout.tsx`. Нельзя править `FfFbsOrdersScreen`, `FfFbsSupplyWorkspace`, `FfFbsStockSyncScreen`, `WildberriesScreen` или их API clients. Минимальный набор selector contracts: `nav-ff-ozon`, `ozon-account-select`, `ozon-sync-health`, `ozon-module-tabs`, `ozon-fbs-queue`, `ozon-posting-next-action-{id}`, `ozon-scan-location`, `ozon-scan-product`, `ozon-unit-identifier-{id}`, `ozon-package-lines`, `ozon-label-status`, `ozon-handover-preflight`, `ozon-fbo-queue`, `ozon-cargo-zone`, `ozon-tgm-zone`, `ozon-acceptance-act`, `ozon-returns-queue`, `ozon-return-disposition`, `ozon-catalog-mappings`, `ozon-warehouse-binding` и `ozon-account-health`.

### Routes и экраны

1. **`/app/ff/ozon` → FBS queue.**
   - Header: «Ozon», seller/account selector, freshness text и account health Alert. Selector нужен, чтобы сотрудник не смешал два кабинета одного seller.
   - Tabs: `К сборке`, `В работе`, `К сдаче`, `Переданы`, `Проблемы`; filters deadline/warehouse/handover/blocker/search.
   - Columns ровно: `Отправление и срок`, `Товары`, `Селлер и склад`, `Сдача`, `Следующий шаг`. В `Товары` показывать `2 позиции · 3 шт.`, а detail раскрывает lines; это сохраняет читаемую очередь и не прячет объём работы.
   - Primary row action: только вычисленный next action (`Связать товар`, `Начать подбор`, `Продолжить маркировку`, `Печатать`, `Подтвердить передачу`, `Разобрать проблему`).
   - States: loading skeleton, empty per tab, stale partial sync, no account, no mapping, shortage, cancelled after pick, unknown status.

2. **`/app/ff/ozon/fbs/:postingId` → FBS workspace.**
   - Sticky summary: posting number, deadline, route, external/local status, `2 позиции / 3 единицы`, last Ozon update.
   - Stepper: `Проверка → Подбор → Данные единиц → Упаковка → Этикетка → Сдача → Подтверждение`. Stepper показывает физическую работу и не разрешает перескочить blocker.
   - `Проверка`: lines with mapping, required qty, reserve and warehouse; admin-only mapping dialog.
   - `Подбор`: scan location field with autofocus, then scan product; picked counters and last scan undo. Сначала ячейка, потому что movement должен иметь физический источник.
   - `Данные единиц`: one card/row per unit; only required KIZ/IMEI/GTIN/weight/country inputs; local and Ozon validation statuses separately; correction dialog before freeze.
   - `Упаковка`: WMS box selector, package composition table with per-line quantities, restrictions Alert, partial package dialog.
   - `Этикетка`: async requesting/ready/error states, preview, `Печать`, `Этикетка нанесена`; superseded warning.
   - `Сдача`: radio-like cards only for discovered modes one-by-one/carriage/manual; each explains required physical handover. Primary action always opens preflight dialog listing passed checks and blockers.
   - `Подтверждение`: timeline `Передано WMS → Ozon сканирует → Доставляется → Доставлено`; arbitration action shift-lead only.

3. **`/app/ff/ozon/fbo` → FBO plans/supplies.**
   - Tabs: `Черновики`, `Таймслот`, `Готовим груз`, `К сдаче`, `Приёмка Ozon`, `Расхождения`, `Завершены`.
   - Columns: `Заявка`, `Маршрут и таймслот`, `Состав`, `Грузоместа`, `Приёмка`, `Следующий шаг`. Отдельные planned/packed/accepted counts нужны для построчной сверки.
   - Primary `Создать поставку FBO` открывает wizard: seller/account → source WMS warehouse → mode → destination → product quantities → capability summary. Недоступный mode виден disabled с конкретной причиной, чтобы планировщик не строил невозможный маршрут.
   - Loading/empty/partial async/error/unknown state fixtures обязательны.

4. **`/app/ff/ozon/fbo/:supplyOrderId` → FBO workspace.**
   - Stepper: `Черновик → Таймслот → Состав → Подбор и упаковка → Грузоместа → ТГМ → Этикетки → Сдача → Приёмка и акт`.
   - Draft/timeslot показывают operation pending/uncertain and readback action; кнопки не становятся success до result.
   - Cargo zone: слева WMS boxes, справа Ozon cargo; drag/drop не нужен — checkbox dialog `Связать`, потому что сканер/клавиатура надёжнее для склада. TGM отдельная zone над cargo membership.
   - Labels list per cargo/TGM with version/status and applied checkbox action.
   - Acceptance act table: `Товар`, `План`, `Принято`, `Отклонено`, `Причина`; primary action `Согласовать акт` только при capability, иначе `Открыть инструкцию ручной проверки`.

5. **`/app/ff/ozon/returns` and `/returns/:id` → returns queue/workspace.**
   - Tabs: `Ожидаются`, `К получению`, `На осмотре`, `Решение`, `Закрыты`, `Не сопоставлены`.
   - Columns: `Возврат`, `Источник FBS/FBO`, `Товар и количество`, `Точка/срок`, `Следующий шаг`.
   - Workspace scan posting/return/product barcode, shows masked exemplar identity, creates quarantine inbound, then inspection dialog: packaging intact, product condition, marking match, photo placeholder, disposition. Default selected state отсутствует; сотрудник обязан осмотреть единицу.

6. **`/app/ff/ozon/catalog` → catalog and bindings, admin.**
   - Two tabs: `Товары` and `Склады и доставка`.
   - Products columns: Ozon product/offer/SKU, barcode, Ozon status/requirements, WMS product, mapping state, action. Link dialog shows exact candidate reason and requires confirm.
   - Topology is a labeled form, not one ambiguous dropdown: physical WMS warehouse, scheme, seller warehouse, destination/cluster, delivery method, return point. Summary sentence describes resulting physical route before save.

7. **`/app/ff/ozon/connection` → account health, admin.**
   - Account cards by seller with masked `Client-Id`, key present boolean, auth mode, external identity, roles, expiry, last discovery/sync, read-only/writes capability matrix.
   - Dialog requires both direct credentials before `Проверить подключение`; incomplete fixture shows zero live calls.
   - Capability matrix groups `Чтение`, `FBS операции`, `FBO операции`, `Документы`; строка stock publishing отсутствует целиком. Отдельный permanent Alert: «Остатки Ozon в этой версии только читаются; публикации из WMS нет» объясняет операционную границу администратору.

### Realistic fixtures

- Seller `Loviana`: действующий WB account (только summary badge) и Ozon account `Ozon Loviana`; этим доказывается одновременное сосуществование без смешения.
- Account `Fashion`: только Api-Key, нет Client-Id, `pending_credentials`, discovery не выполнялся.
- FBS `4829-0001-1`: two lines / three units, одна line mapped, одна unmapped.
- FBS `4829-0002-1`: KIZ + IMEI required, один exemplar accepted, один rejected.
- FBS `4829-0003-1`: partial package creates second posting/package, label task pending then ready.
- FBS `4829-0004-1`: cancelled after pick and requires return-to-cell scan.
- Один one-by-one handover и одна compatible carriage с act pending; один handed-over posting without Ozon scan for arbitration.
- FBO direct plan: 3 lines, pending timeslot operation, 2 cargo inside 1 TGM, one failed cargo label.
- FBO acceptance act: planned 10, accepted 9, rejected 1 with reason.
- FBS linked return, FBO return and unmatched return; all enter quarantine.
- 429 retry banner, partial pagination, expired credential, unknown external status and stale last-success data.

### Prototype acceptance before implementation

Product Agent must use a visible real browser and record URL, role, seller/account, clicks and visible outcomes for:

1. Admin connects full fixture account, sees identity/capabilities, links a product and saves a full FBS binding.
2. Operator processes multi-item FBS through scan, exemplar correction, partial package, label and one-by-one handover without seeing stock publication.
3. Operator recovers cancelled-after-pick posting into a scanned location.
4. Planner creates FBO plan, waits through async state, assigns cargo to TGM, prints labels and reviews a discrepancy act.
5. Reception receives unmatched return into quarantine and cannot restock before inspection/mapping.
6. Admin switches between seller with simultaneous WB+Ozon and incomplete Ozon account; no data leaks across account selector.
7. Error/empty/loading/partial/uncertain states keep the last confirmed data and expose exactly one safe next action.

Verdict must be `PRODUCT_BROWSER_APPROVED` for the prototype contract before BA cards for production implementation are frozen. Prototype approval is not production acceptance.

## 18. Test architecture

### Contract and adapter tests

- Version-frozen sanitized request/response fixtures for every used endpoint family, including unknown fields/enums.
- Pagination tests for cursor, offset/limit, `last_id/has_next`, time windows and page-resume after commit failure.
- 401/403/429/5xx, retry headers, expiry, identity mismatch and schema drift.
- Push duplicate/out-of-order/invalid-auth; poll-only fallback must converge to the same state.
- Outbound recorder asserts secrets only in headers and sanitized logs contain no Api-Key, OAuth token or full marking code.

### Domain/integration tests

- Same seller with WB and two Ozon accounts: product IDs, checkpoints, operations and documents remain account-scoped.
- FBS multi-line/quantity reservation, shortage, scan idempotency, exemplar correction/freeze, partial package quantity invariants, cancel before/after pick, label supersession, one-by-one vs carriage, uncertain ship readback, arbitration.
- FBO draft/timeslot/supply async states, composition revisions, cargo rules, partial cargo failure, TGM membership, label versioning, physical/external handover split, acceptance discrepancy/act.
- Returns linked/unmatched, duplicate external event, quarantine inbound, no inventory increase before posted disposition.
- Existing WB backend and Playwright suites remain required regression gates; zero legacy table migration.

### API/security tests

- Tenant/seller/account IDOR attempts, delegated seller scope, permission matrix and disabled account.
- Idempotency key conflict, active intent uniqueness, readback-before-retry and shift-lead-only recovery.
- Document path is internal-only; content route validates tenant/entity and rejects superseded asset as primary print.
- Deny-by-construction stock suite from section 15 runs on every Ozon-related PR.

### UI/browser tests

- Each production slice adds Playwright user-visible scenarios with `TC-Sxx-yyy`/`TC-NEW-*` traceability, stable `data-testid`, realistic local Ozon emulator, and no external network.
- Playwright covers actions and visible outcome, but final Product Browser Review uses a visible real browser and is separately recorded.
- Visual golden tests apply to generated/normalized print layouts only after source size is confirmed; binary pass-through documents use checksum/content-type tests and a manual print sample gate.

## 19. Vertical slices: сумма равна полному модулю

Каждый slice — отдельные BA feature cards и проходит `BA_READY → PRODUCT_APPROVED_FOR_DEV → DEV_DONE → CODE_REVIEW_PASSED → PRODUCT_BROWSER_APPROVED`. Общие machine gates каждого PR: backend `ruff check . && mypy . && pytest`, migration from zero/upgrade test, frontend `npm run build && npm run test:e2e` при UI, contract emulator without network, relevant WB regression suite, commit/push evidence. После всех slices нужны integration review и общий live-browser regression.

| Slice | Пользовательский результат | Зависимости | Recovery/negative gate | Completion criteria |
|---|---|---|---|---|
| S0 Clickable prototype | Весь процесс можно пройти на fixtures до кода | Эта архитектура | Все states из задания, no production API | Prototype `PRODUCT_BROWSER_APPROVED` |
| S1 Account and capability discovery | Admin безопасно подключает/проверяет Ozon account; incomplete pair не вызывает сеть | S0 | identity mismatch, expiry, missing role, no secret leakage | account health browser accepted; read-only live smoke only если позже есть полная пара и отдельное разрешение |
| S2 Catalog, mappings and topology | Admin импортирует товары/nodes, подтверждает mapping и FBS/FBO bindings | S1 | ambiguous mapping, missing node, account isolation, partial pagination | full local backfill+resume; catalog/topology browser accepted |
| S3 Reliability spine | Пользователь видит truthful job/partial/operation/document states | S1 | 429, timeout uncertain, duplicate push, readback-before-retry | emulator fault matrix green; push may remain disabled with poll fallback |
| S4 FBS intake/reserve/pick | Operator receives multi-line postings, reserves by line and scans location/product | S2,S3 | shortage, cancel before/after pick, duplicate scan, unknown status | inventory invariants and FBS queue/workspace browser accepted |
| S5 FBS exemplars/package/label | Operator submits required unit data, packs quantities and prints current label | S4 | rejected exemplar, partial package, incorrect dimensions, label pending/superseded | unit/package invariants, print sample and browser accepted |
| S6 FBS handover/acts/recovery | One-by-one and capability-driven carriage reach confirmed external lifecycle | S5 | timeout uncertain, missing scan/arbitration, manual portal fallback | no false delivered state; recovery queue and browser accepted |
| S7 FBO plan/draft/timeslot/supply | Planner creates supported FBO route through async supply order | S2,S3 | unsupported mode, operation timeout, timeslot conflict, revision | emulator async lifecycle and browser accepted |
| S8 FBO packing/cargo/TGM/labels/handover | Warehouse prepares and transfers traceable cargo/TGM | S7 | partial cargo error, rules drift, failed/superseded label | per-cargo recovery, print sample and browser accepted |
| S9 FBO acceptance act/reconciliation | Planner sees acceptance/stock appearance and resolves act discrepancy | S8 | beta capability absent, rejected act, manual fallback | no conflation of WMS handover/Ozon acceptance; browser accepted |
| S10 Unified Ozon returns | Reception receives FBS/FBO returns into quarantine and disposes after inspection | S4,S7,S3 | unmatched/duplicate/damaged, no auto-restock | inbound+inventory invariants and returns browser accepted |
| S11 Cross-module integration and hardening | Dashboard/catalog filters, audit/recovery, seller read-only views, full coexistence | S4–S10 | two accounts + WB regression, performance/backfill, kill switches | all gates green, integration review, final visible-browser regression, deployed SHA proof if release requested |

Полный Ozon module означает завершённые S0–S11, а не ранний account/catalog slice. Если отдельная capability недоступна реальному account, модуль всё равно функционален через discovery и документированный manual/read-only fallback; нельзя называть недоступный внешний feature реализованным.

## 20. Conscious non-goals

- Не переписывать и не мигрировать `FbsOrder`, `FbsSupply`, `FbsTrbx`, WB credentials/routes/jobs/screens/print tape/stock sync.
- Не делать общий lifecycle enum, в котором Ozon и WB обязаны пройти одинаковые stages.
- Не создавать и не редактировать карточки Ozon (`product import/update`) в этой программе slices.
- Не публиковать FBS-остатки Ozon и не создавать скрытую/disabled кнопку для этого.
- Не исследовать сейчас Yandex Market API; будущая площадка переиспользует core только после своего research gate.
- Не автоматизировать решения по качеству возврата, арбитражу или acceptance discrepancy.
- Не гарантировать формат этикетки, cargo rule, таймслот или capability без version-frozen schema/real response.
- Не redesign-ить dashboard, WB FBS, общий каталог или «Отгрузки» шире точечных фильтров/ссылок, перечисленных в section 16.
- Не считать prototype, unit/Playwright tests, local URL или HTTP 200 доказательством production deployment или внешнего приёма Ozon.

## 21. Риски и меры

| Риск | Мера |
|---|---|
| Потерять quantity/unit при помещении Ozon в WB order | Ozon-native line/unit/package tables и quantity constraints |
| Смешать accounts одного seller | `marketplace_account_id` во всех external keys/checkpoints/operations/assets + tenant checks |
| Дважды создать draft/ship/cargo после timeout | immutable ledger, uncertain state, mandatory readback before any new intent |
| Пропустить postings из-за push/pagination | poll authority, versioned checkpoint, transactional page commit and bounded backfill |
| Ложно показать delivered/accepted | separate WMS physical and external states; transition only on readback |
| Неверно списать/вернуть inventory | WMS inventory/packaging remain authority; compensating movements and quarantine returns |
| Напечатать старую/неверную этикетку | taxonomy, source/version/checksum/supersession/applied audit, print sample gate |
| Сломать WB | additive tables/routes, no legacy data rewrite, mandatory full WB regressions |
| API drift/beta changes | operation matrix, version namespace, unknown enum tolerance, feature-specific kill switch |
| Утечка credentials/marking codes | encryption, masked API, sanitized payloads, header-only secrets, audit hashes |
| Operator overload | one next action, bounded columns, blockers attached to work, Product real-browser gates |

## 22. Вопросы владельцу

**Вопросов владельцу: 0.** Владелец делегировал решения ведущему и попросил не прерывать его. Архитектурные решения приняты выше; неизвестные внешние факты не превращаются в блокирующие вопросы.

Остаются только пять внешних фактов, каждый имеет безопасный fallback:

1. **Фактическая identity/roles/expiry и поддерживаемый auth mode account.** Fallback: account `pending_credentials`/`active_read_only`; без полной пары нет live call, OAuth добавляется отдельным adapter slice после подтверждения.
2. **Доступные конкретному account FBS handover modes и FBO route capabilities.** Fallback: использовать discovery + entity `available_actions`; недоступное действие заменяется manual portal instruction и readback.
3. **Текущие точные OpenAPI schemas и размеры/форматы package/cargo/TGM/act assets.** Fallback: capability off до version-frozen fixture; binary pass-through без resize и ручной print sample.
4. **Реальные cargo/TGM rules, destinations и limits для ассортимента/маршрута.** Fallback: читать rules после создания supply; до ответа сохранять local plan, но не submit cargo.
5. **Операционная политика владельца по спорным/повреждённым returns.** Fallback: quarantine и `needs_shift_lead`; автоматический restock запрещён.

## 23. Definition of architecture done и передача следующему этапу

Этот документ считается Stage-0 архитектурным артефактом, когда он сохранён отдельным commit/push и ведущий подтвердил, что он покрывает owner request и accepted research. Он не создаёт `BA_READY` или `PRODUCT_APPROVED_FOR_DEV` автоматически.

Следующее разрешённое действие ведущего — поручить bounded clickable React prototype из section 17. После visible-browser принятия прототипа BA Agent режет S1–S11 на атомарные feature cards; Product Agent принимает каждую карточку до разработки. Production implementation не должна начинаться с «универсального рефакторинга WB» или с live Ozon mutation.
