# S0R: обязательный контракт семантического переиспользования Ozon

**Call ID:** `17-ozon-semantic-reuse-contract-rework`

**Дата:** 24 августа 2026 года

**Исходный Git baseline:** `2af800d5846d351904cab050860356038b6d282e`

**Живой UI baseline:** приложение `af0779e1c425eede8d811da666822ff6ed178331`, без `ozonPrototype`

**Отклонённое свидетельство:** `309e85d666f377e23e670d0ae0044f12ca4449cd`; оно не является продуктовым доказательством
**Статус:** обязательный product/architecture contract до нового кликабельного прототипа; application и prototype code этим документом не меняются и не разрешаются

## 1. Решение и неизменяемая граница

Ozon не получает отдельный модуль в навигации. Он входит условной marketplace-дельтой в существующие складские работы:

- FBS — `/app/ff/fbs`, текущая очередь и тот же `FfFbsSupplyWorkspace`;
- FBO — `/app/ff/mp-shipments`, текущий create block и тот же полноэкранный документ;
- возврат — `/app/ff/reception`, текущая очередь и та же карточка документа;
- товар — `/app/ff/products`, текущая таблица, action-zone и существующий product dialog;
- подключение — `/seller/settings`, соседняя карточка и тот же credentials-dialog pattern.

Target содержит **0** новых routes, screens, pages, tabs, documents, workspaces, modals, navigation items и лишних операторских шагов. Условная Ozon-ветка имеет право менять поля, подписи, допустимые действия и состояния только внутри перечисленных существующих зон. Ранний `return` целого Ozon screen/workspace, Ozon-only modal, фиксированные декоративные tabs и второй action с тем же намерением считаются новым surface даже внутри разрешённого файла.

WB остаётся baseline. Общий UI-контракт расширяется только через marketplace adapter и capabilities; Ozon не записывается в `wb_*`, а WB не переводится на новую модель в этой программе.

## 2. Primary user и работа

**Primary user — оператор фулфилмент-склада.** Он должен в одной привычной очереди понять, что именно собрать, доказанно взять товар из WMS-ячейки, выполнить требования конкретного маркетплейса, упаковать и передать груз, не создав ложного завершения.

Каждый заметный элемент имеет конкретную работу:

- `Маркетплейс` в существующем фильтре не украшает строку: он не даёт смешать WB и Ozon, для которых различаются этикетки и сдача.
- `2 товара · 3 шт.` в строке Ozon говорит оператору реальный объём; одно отправление Ozon может содержать несколько товарных линий и количеств.
- Отдельные `Подобрано`, `Упаковано` и `Осталось подобрать` защищают от физически невозможного состояния, когда упаковки больше, чем подобранного товара.
- Статус проверки кода по каждой единице нужен, чтобы оператор исправил отклонённый код до упаковки, а не принял локальный скан за подтверждение Ozon.
- `Этикетка готовится`, `Этикетка готова`, `Этикетка наклеена` разделены, потому что асинхронное создание файла не доказывает печать и нанесение.
- В FBO грузоместо Ozon и транспортное грузоместо показаны рядом с текущим WMS-коробом, потому что физический короб не доказывает корректную внешнюю структуру поставки.
- Осмотр возврата обязателен по каждой единице, потому что статус возврата Ozon не доказывает совпадение товара и пригодность к продаже.
- Внешнее неподтверждённое состояние остаётся рядом с инициировавшим действием, чтобы следующая смена сначала проверила факт, а не повторила операцию и не создала дубль.

Secondary users: seller admin подключает кабинет и видит срок/доступность; FF-admin подтверждает связь товара; бригадир планирует FBO и разбирает расхождения; сотрудник приёмки осматривает возврат. Их действия остаются на текущих страницах.

## 3. Нормальный процесс

### 3.1 Подключение и товар

1. Seller admin открывает `/seller/settings`. WB-card не меняется. Соседняя Ozon-card содержит ровно действия `Добавить подключение` или `Изменить подключение` и `Синхронизировать товары и справочники`.
2. Тот же credentials dialog открывается с заголовком `Подключение Ozon`, полями `Client-Id` и `API-ключ`, действиями `Сохранить` и `Закрыть`. Неполная пара показывает `Укажите Client-Id и API-ключ`; внешний запрос не выполняется.
3. После проверки карточка показывает `Подключение проверено`, `Кабинет: …`, `Доступ до: …`, `Последняя успешная синхронизация: …`. Неуспех показывает операторскую причину, не HTTP/status-code.
4. FF-admin открывает `/app/ff/products`. В существующей action-zone строки действие `Связь с Ozon` раскрывает кандидатов **внутри строки**, без нового dialog. `Подтвердить связь` доступно только для выбранного кабинета и точного внешнего товара; `Отклонить вариант` оставляет WMS SKU неизменным.
5. Существующий `Создать товар` dialog сохраняет WMS-идентичность. При наличии Ozon-card он получает только пояснение: `Сначала создайте товар в WMS. Связь с Ozon подтверждается в строке товара.` Новых полей маркетплейса в этом dialog нет.

### 3.2 FBS

1. Оператор остаётся в `/app/ff/fbs`, выбирает `Маркетплейс: Ozon` и видит Ozon postings в текущих статусных группах. Вкладка `Остатки WB` и действие `Забрать заказы из WB` не показываются внутри Ozon-context; вместо внешней синхронизации есть одно действие `Получить отправления Ozon`.
2. Одна строка соответствует одному Ozon posting. Она показывает `Отправление Ozon №…`, первые товарные линии и итог `N товаров · M шт.`. Несопоставленная линия блокирует checkbox с причиной `Товар не связан с каталогом WMS`; исправление выполняется в текущем каталоге, а не в новом FBS dialog.
3. После однородного выбора selection bar содержит одно действие открытия — `Начать сборку`. Оно создаёт локальную рабочую группировку и открывает тот же modal. Это не внешняя поставка Ozon и не дополнительный документ.
4. `Состав`: оператор видит все линии/количества и нажимает `Начать сборку`. Заголовок показывает `Отправление Ozon №…` и `Передать в Ozon до …`; названия четырёх стадий не меняются.
5. `Подбор`: скан WMS-ячейки и товара увеличивает picked ровно на одну единицу нужной линии. Лишний, чужой или повторный скан отклоняется до движения остатка. Если действует текущий auto-pass, UI показывает `Подбор учтён автоматически: товар не распределён по адресным ячейкам. Подготовлено 3 из 3.` и хранит `picked = plan = 3`, а не `picked = 0`.
6. `Упаковка и маркировка`: только требуемые для единицы поля отображаются как `Код маркировки`, `IMEI`, `GTIN`, `Вес`, `Страна происхождения`. Состояния: `Код сохранён` → `Ozon проверяет код` → `Код принят` либо `Ozon отклонил код: …`; действие исправления — `Исправить код`. Для fixture с тремя единицами действия названы `Упаковать 2 из 3` и `Упаковать оставшуюся единицу`; частичная упаковка показывает `Упаковано 2 из 3`, не закрывая posting.
7. `Короба`: текущая зона показывает связь WMS-короба с упаковкой Ozon и состояния `Этикетка готовится` → `Этикетка готова` → `Этикетка наклеена`. При обнаруженной возможности поштучной сдачи единственное действие — `Передать поштучно`; результат — `Передано со склада. Подтверждение Ozon ещё не получено.` Локальная передача не становится `Доставлено`.

### 3.3 FBO

1. На `/app/ff/mp-shipments` в текущем create block рядом с seller появляется `Маркетплейс`; кнопка остаётся `Создать отгрузку на МП`. При WB выбранном значении дополнительных полей и изменений нет.
2. В том же документе Ozon заменяет только provider-specific поля: `Склад Ozon`, `Схема поставки`, `Интервал приёмки`. Асинхронные состояния написаны `Заявка создаётся`, `Заявка создана`, `Не удалось создать заявку`, `Состояние заявки не подтверждено. Проверьте его перед повтором.`
3. Tabs остаются `Товары`, `Подбор`, `Упаковка`. В Ozon-context `Артикул WB` становится `Артикул Ozon`, `Категории WB` — `Категории Ozon`; общие SKU/ШК/quantity поля не меняются.
4. Метрики всегда происходят из одной модели: `План`, `Подобрано`, `Осталось подобрать`, `Упаковано из подобранного`. Физическая работа использует существующие reserve/pick/PackagingTask/WMS boxes.
5. В существующей `Упаковке` после WMS boxes условно показаны `Грузоместо Ozon` и `Транспортное грузоместо`. Рядом дано короткое объяснение: `Грузоместо Ozon — часть поставки; транспортное грузоместо объединяет груз по правилам выбранной схемы.` Этикетка привязана к своему объекту, а не называется WB QR.
6. Footer сохраняет существующие `Утвердить`, `Завершить`, `Отменить отгрузку`, `Закрыть` по текущему lifecycle. После локального завершения тот же документ различает `Передано со склада`, `Принято Ozon`, `Отклонено Ozon` и `Акт приёмки согласован`; отсутствие возможности согласовать акт показывает `Требуется проверка в кабинете Ozon`, без ложной автоматизации.

### 3.4 Возврат

1. Ozon return появляется в общей очереди `/app/ff/reception` как тип `Возврат`; в существующем extra-text — `Ozon · возврат №…`. Новых фильтров, tabs и документов нет.
2. Строка открывает ту же карточку. Header сохраняет тип, номер, seller, принято, короба, литраж, вес и статус. Черновик сохраняет `Добавить товар`, `Начать приёмку`, `Сохранить`, `Закрыть`.
3. Для каждой принятой единицы текущая строка показывает `Осмотр не выполнен`. Оператор отмечает `Товар совпадает` или `Товар не совпадает`, `Без повреждений` или `Есть повреждения`, затем нажимает `Завершить осмотр`.
4. До этого решения `Вернуть в продажу`, `Оставить отдельно`, `Зафиксировать брак` отключены. После осмотра оператор выбирает ровно один исход. Только `Вернуть в продажу` разрешает существующему inbound posting создать движение в доступный остаток.

## 4. Ошибки и частичные состояния

| Ситуация | Что видит пользователь | Допустимое следующее действие | Запрещённая ложь |
|---|---|---|---|
| Неполные данные подключения | `Укажите Client-Id и API-ключ` | `Изменить подключение` | `Подключено` и любой внешний вызов |
| Частично загружены справочники | `Синхронизация выполнена частично. Последние подтверждённые данные сохранены.` | `Продолжить синхронизацию` | обнулить прошлые подтверждённые данные |
| Товар не связан | `Товар не связан с каталогом WMS` | `Перейти к товару` | начать reserve/pick |
| Неизвестное внешнее состояние | `Требуется проверка состояния в Ozon` | `Проверить состояние` | показывать успешное завершение или повторять действие |
| Код единицы отклонён | `Ozon отклонил код: <операторская причина>` | `Исправить код` | упаковать эту единицу |
| Этикетка ещё не готова | `Этикетка готовится` | автоматическое ожидание; при длительной задержке `Проверить состояние` | печатать старую/неполную этикетку |
| Частичная упаковка | `Упаковано 2 из 3` | упаковать остаток либо обработать разрешённый split | считать posting готовым целиком |
| Таймаут после внешнего действия | `Состояние не подтверждено. Проверьте его перед повтором.` | `Проверить состояние` | кнопка слепого повтора |
| FBO принято частично | `План 10 · принято 9 · отклонено 1` + причина по строке | ручная сверка/акт, если capability подтверждена | `Принято` для всего документа |
| Возврат не осмотрен | `Осмотр не выполнен` | заполнить осмотр | доступный restock |
| Возврат повреждён/не совпал | `Оставлен отдельно` либо `Зафиксирован брак` | действие руководителя по текущему регламенту | автоматический restock |

## 5. Граница систем и ручных действий

**WMS отвечает** за tenant/seller/account isolation; WMS product/warehouse/location; резерв и движения; local picked/packed; существующие work batches, shipments, boxes и inbound documents; audit; безопасное хранение secrets/assets; отображение последнего подтверждённого внешнего факта; запрет недопустимого действия.

**Ozon отвечает** за account identity/roles; offer/product/sku; posting lines и `available_actions`; проверки экземпляров; package restrictions/labels; FBS handover confirmation; FBO route/timeslot/supply/cargo/TGM/acceptance; returns feed; внешние ошибки и лимиты. HTTP success не равен бизнес-успеху.

**Ручными остаются** фактический скан/подбор/упаковка/наклейка/передача; осмотр возврата; выбор disposition; разбор расхождения; действие в кабинете Ozon, если API capability отсутствует. WMS фиксирует ручной факт, но не выдаёт его за подтверждение Ozon.

## 6. Данные и API

Target-модель — additive seam, не patch этой задачи:

- `marketplace_accounts` scoped `tenant_id + seller_id + marketplace`; credential references, external identity, roles, expiry, capabilities;
- `marketplace_product_mappings` scoped by account; `offer_id`, `product_id`, `sku`, barcodes, WMS product, status/history;
- `marketplace_nodes`/bindings для seller warehouse, delivery method, Ozon warehouse, return point и WMS warehouse/location без слияния сущностей;
- checkpoints per account/resource/API-version/filter; event inbox with deduplication; operation ledger with intent fingerprint and authoritative state check before retry;
- Ozon FBS `posting → lines → units/required data → packages → package lines`; local work batch is not Ozon supply/carriage;
- Ozon FBO link under existing `MarketplaceUnloadRequest`: supply order, route/interval, cargo, transport cargo, labels, acceptance/act;
- marketplace return linked one-to-one to existing `InboundIntakeRequest(operation_type="return")` and per-unit inspection/disposition;
- marketplace assets with kind/source/version/checksum/status/supersession; product barcode, posting/package label, cargo label, transport-cargo label and act are distinct.

Frontend остаётся на существующих API families:

- accounts/discovery/sync: additive `/integrations/marketplaces/self/accounts...`; WB `/integrations/wildberries/*` stays compatible;
- catalog mapping: additive data in `/products/ff-catalog` and product-scoped mapping command;
- FBS queue/workspace: existing `/operations/fbs-orders/...` and `/operations/fbs-supplies/...`, provider server-resolved from stored entity;
- FBO: existing `/operations/marketplace-unload-requests/{id}/...` with Ozon children;
- return: existing `/operations/inbound-intake-requests/{id}/...`, inspection under existing line resource; stock posting remains current inbound movement.

Ozon product publication and `/v2/products/stocks` are absent by construction: no route, client method, job, capability or UI action.

## 7. Переиспользуемые части WMS

Без изменения смысла используются `Tenant`, `Seller`, `Product` as WMS identity, `Warehouse`, `StorageLocation`, inventory movement/reservation, `PackagingTask`, `MarketplaceUnloadRequest`, inbound request/boxes, job shell, encrypted-secret pattern, binary asset storage, roles, audit and текущие MUI surfaces.

Через узкий facade используются current FBS worklist/workspace, scan flows, print/applied interaction and MP shipment stage engine. Facade обязан сначала доказать WB projection equality.

Не становятся общим truth: `FbsOrder.wb_*`, `FbsSupply.wb_supply_id`, `FbsTrbx`, WB status maps/publisher, `Product.wb_*`, один marking `mp_api_key`, WB sticker/trbx/supply QR taxonomy и универсальная пагинация/retry.

## 8. Варианты и цена

1. **Положить Ozon в текущие WB rows/models.** 6–9 недель, но multi-line quantity/package будут потеряны, а one-by-one handover станет ложной WB-supply. Цена исправления и риск остатков критические. Отклонён.
2. **Additive Ozon aggregates + adapters/capabilities на текущих surfaces.** 12–18 инженерных недель, ориентировочно 8–12 atomic slices с fixtures, migrations, WB characterization, printing и browser gates. Это выбранный вариант: физическая работа и UI переиспользуются, Ozon semantics не стираются.
3. **Сразу мигрировать WB и Ozon на canonical marketplace domain.** 20–30+ недель, backfill и переключение всего WB lifecycle. Архитектурно чище позже, но несоразмерно опасно сейчас. Отложен.

## 9. Сознательные non-goals

- Ни одного нового UI surface или Ozon navigation.
- Ни одного изменения WB copy/action/state/network contract вне отдельной owner-approved feature card.
- Нет production/prototype code в этом call.
- Нет product/stock publication, автоматического split/cancel/retry/restock или act acceptance.
- Нет догадок о реальном account, roles, routes, labels, cargo rules, quotas или форматах.
- Нет Yandex/других marketplace integrations.
- Нет заявления `готово`, deploy или browser approval по этому архитектурному артефакту.

## 10. Риски

- **Семантическая подмена внутри разрешённого файла.** Gate запрещает ранний whole-screen return, Ozon-named replacement component и Ozon-only modal.
- **WB regression.** WB browser path, visible copy, action intents, request traces and geometry сравниваются с baseline до принятия shared change.
- **Противоречивый прогресс.** Один selector вычисляет plan/picked/packed/remaining; mutation и render используют его же.
- **Дубль внешней операции.** Active intent fingerprint + обязательная проверка authoritative state до нового send.
- **Ранний restock.** Server и UI gate требуют completed per-unit inspection plus disposition.
- **Неверная этикетка.** Asset kind/version/checksum/supersession и ready/current-only print.
- **Account leak.** Authorization order tenant → seller → marketplace account на каждом external key.
- **API drift.** Version-frozen sanitized fixtures, unknown-enum tolerance, capability off by default.
- **Узкие экраны.** Числовые geometry assertions ниже не допускают увеличения уже существующего overflow.

## 11. Вопросы владельцу

**Вопросов владельцу: 0.** Owner override уже зафиксировал product boundary. Неизвестные account capabilities, label formats, cargo rules и return policy не заполняются догадками: действие скрыто или заблокировано с операторской причиной; manual fallback не имитирует Ozon success.

## 12. Binding side-by-side contract

Каждая строка обязана пройти на desktop `1600×1111` и narrow `433×938`. `Same render` означает тот же component tree/route/modal/stage engine; conditional adapter payload допустим, whole-screen replacement запрещён.

| ID | Baseline evidence и invariant | Единственная минимальная Ozon-дельта на той же зоне | Почему Ozon требует | WB regression invariant | Исполнимая проверка |
|---|---|---|---|---|---|
| FBS-Q | `01`, `02`; `/app/ff/fbs`, `Заказы FBS`, current tabs/filters/tables, row opens same modal; desktop body 1600, main 1340, table 1290.89 | один `Маркетплейс` filter; Ozon-context copy `Получить отправления Ozon`, posting/line totals in current cells; one `Начать сборку` | multi-line posting and different labels/handover | WB filter default, `Забрать заказы из WB`, `Остатки WB`, status groups, columns, selection/supply actions unchanged | same `fbs-orders-screen`; no new route/tab/column; `action-intent=open-fbs-workspace` count=1; scoped WB-regex=0 in Ozon; WB visible-text/request snapshot equal; desktop bounds ≤ baseline, narrow body ≤433 |
| FBS-C | `12`; same modal, `Состав`, two rows, one `Начать работу с поставкой`; dialog 1500×1044 | same stage renders posting lines/qty; header `Отправление Ozon`, action `Начать сборку` | posting has lines/quantities and may not have carriage | WB title/header/`Заказ WB`/button/stage order unchanged | `fbs-workspace` identity stable; exactly four stage labels; Ozon button count=1; plan=sum line qty |
| FBS-P | `14`, `15`; same `Подбор`, scanner fields/read-only auto-pass; narrow dialog 369×874, no internal overflow | quantity picking; explicit auto-pass `Подготовлено N из N` with picked=plan | quantity >1 and current auto-pass would otherwise make packed>picked possible | WB scans, readonly reason and transition unchanged | after every click `0≤packed≤picked≤plan`; auto-pass assertion `picked=plan && reason visible`; wrong/repeat scan leaves counts; narrow `scrollWidth=clientWidth≤369` |
| FBS-U | `13`; same `Упаковка и маркировка`, print/bulk/scan/rows | per-unit required fields, correction, package qty and Russian label states in current rows/print zone | validation and partial package are Ozon-native | WB print, ЧЗ, order sticker and bulk packing unchanged | rejected unit disables package completion; correction enables; state 2/3 keeps stage incomplete; jargon regex=0; packed never exceeds picked |
| FBS-B | same modal fourth stage `Короба`; baseline stage geometry from `12`–`15` | WMS box↔Ozon package, current label, one capability-derived handover action in existing bottom zone | package label and one-by-one handover differ from WB trbx/supply | WB boxes/trbx/supply QR/deliver unchanged | one `handover` intent; label transitions only preparing→ready→applied; local handover text not delivered; no added stage/workspace; geometry ≤ modal baseline |
| FBO-L | `03`; `/app/ff/mp-shipments`, seller + one `Создать отгрузку на МП`, seven columns | one marketplace select in current create block | account/route is required before Ozon supply | WB selection produces byte-for-behavior same create/list flow | no new route/document/modal; create intent count=1; baseline columns/text equal under WB; no added horizontal overflow versus screenshot |
| FBO-H | `04`, `16`; same fullscreen `Отгрузка на маркетплейс`; current header/4 metrics/3 tabs/footer; desktop 1600×1111, narrow 433×938 internal no overflow | conditional `Склад Ozon`, `Схема поставки`, `Интервал приёмки` and Russian operation state in same header | Ozon draft/timeslot async and route-dependent | WB `Склад WB (маркетплейс)`, hint, metrics and footer unchanged | tabs exactly 3; metric formula; no forbidden jargon/WB text in Ozon document; narrow dialog width≤433 and internal scrollWidth≤433; underlying body≤960 |
| FBO-T | `04`, `05`; same `Товары`, current add/scan/picker/table; `Артикул WB`, WB categories baseline | conditional Ozon labels in same cells/picker, no new field group | offer/SKU/category differ from WB | WB picker/search/table byte-for-behavior unchanged | same dialog/picker testids; Ozon scoped WB-regex=0; plan equals line sum; no new tab/column |
| FBO-P | same document `Подбор`/`Упаковка`, current reserve/pick/PackagingTask/boxes | cargo/TGM links after existing boxes; Russian explanation and per-object label state | Ozon external hierarchy is not a WMS box | WB pick/pack/box interactions and requests unchanged | `packed≤picked`; each external node linked to existing closed box; one print intent per asset; tabs switch real panels, not fixed decoration |
| FBO-F | same footer actions and document lifecycle | separate local handover, Ozon acceptance and act facts inline after finish | shipped/accepted/act are different facts | WB `Утвердить`/`Завершить`/cancel/close rules unchanged | no external success from local click; partial accepted/rejected sum checked; no blind retry; action-intent uniqueness |
| RET-Q | `06`; `/app/ff/reception`, `Создать приёмку`, `Создать возврат`, same filters/queue | `Ozon · возврат №…` in existing extra text | unified Ozon returns feed must enter physical inbound | current manual inbound/return creation and queue unchanged | same queue row opens same `ff-doc-dialog`; no new filter/tab/route; no duplicate row for same external return |
| RET-C | `07`, `08`, `17`; same card/header/actions/table/boxes; desktop 1600×1111, narrow 433×938 no overflow | identifiers + per-unit inspection/disposition in current row; restock disabled until completed inspection | external return status does not prove identity/condition | non-Ozon inbound/return card copy/actions/state unchanged | before inspection restock disabled server+DOM; exactly one disposition; damaged/mismatch never increases available stock; narrow internal scrollWidth≤433 |
| CAT-T | `09`, `18`; `/app/ff/products`, same 2 tabs, actions, filters, 12 columns/action-zone; desktop table1290.89, narrow table1283.99 | `Связь с Ozon` in current action-zone, inline row expansion only | account-scoped offer/product/sku may be ambiguous | WB/WMS columns, tabs, actions and mapping unchanged | no new tab/column/dialog; confirm intent count=1; WMS SKU stable; desktop table≤1290.89, narrow table≤1283.99/body≤433 |
| CAT-D | `10`; existing `Создать товар` dialog and WMS fields | one explanatory sentence only; no Ozon identifiers/fields/actions | prevents operator replacing WMS identity with provider identity | all baseline required fields, save/cancel and geometry unchanged | field/action list exact; no new modal; one added text node only when Ozon account exists |
| SET-C | `11`, `19`; `/seller/settings`, staff then WB card/actions then ЧЗ; desktop body1600, narrow body1084/main843.81 | one neighboring Ozon card; same credentials-dialog pattern; exact Russian status/actions | Ozon needs Client-Id+API key, roles/expiry | WB card copy/order/actions/network unchanged | Ozon card root scoped; WB-regex applies only Ozon card/dialog; no new route/tab/modal; WB card DOM/action/request snapshot equal; narrow body≤1084/main≤843.81 |

## 13. Exact Russian UI copy and forbidden text gate

Approved Ozon copy is limited to the phrases in §§3–4 plus:

- labels: `Маркетплейс`, `Ozon`, `Отправление Ozon`, `Склад Ozon`, `Схема поставки`, `Интервал приёмки`, `Артикул Ozon`, `Категории Ozon`, `Грузоместо Ozon`, `Транспортное грузоместо`, `Упаковка Ozon`;
- actions: `Получить отправления Ozon`, `Начать сборку`, `Исправить код`, `Упаковать 2 из 3`, `Упаковать оставшуюся единицу`, `Проверить состояние`, `Подтвердить, что этикетка наклеена`, `Передать поштучно`, `Связать с грузоместом Ozon`, `Добавить в транспортное грузоместо`, `Подготовить этикетку`, `Связь с Ozon`, `Подтвердить связь`, `Отклонить вариант`, `Добавить подключение`, `Изменить подключение`, `Синхронизировать товары и справочники`, `Завершить осмотр`, `Вернуть в продажу`, `Оставить отдельно`, `Зафиксировать брак`;
- states: `Подключение проверено`, `Синхронизация выполнена частично`, `Код сохранён`, `Ozon проверяет код`, `Код принят`, `Ozon отклонил код`, `Этикетка готовится`, `Этикетка готова`, `Этикетка наклеена`, `Передано со склада`, `Подтверждение Ozon ещё не получено`, `Осмотр не выполнен`.

Within `[data-marketplace-context="ozon"]`, case-insensitive visible-text gate fails on `Wildberries`, `WB`, `ВБ`, `Заказ WB`, `Склад WB`, `Артикул WB`, `Сдать в Wildberries`, `заказа в WB`, `fixture`, `projection`, `provider API`, `readback`, `pending`, `uncertain`, `exemplar`, `QUARANTINE`, `mapped`, `local workspace`, `unit projection`, `account-scoped`, `sync fixture`. Test ids/source comments are outside operator-visible text and do not satisfy/fail copy assertions.

## 14. Deterministic machine/browser gates

1. **Surface:** route manifest/nav diff contains no new target; React AST rejects early query-conditional whole-screen returns, new Ozon `*Screen|*Page|*Workspace|*Document|*Modal`, and fixed decorative tabs. Existing render roots/testids must be identical.
2. **Progress:** after mount and every click/scan, for every FBS/FBO item `plan` is integer ≥0, `picked` and `packed` are integers, `0 ≤ packed ≤ picked ≤ plan`, `remaining = plan - picked`. UI text is derived from the same selector. Auto-pass requires non-empty reason, `picked=plan`, `packed≤picked` and read-only picking.
3. **Return:** `inspection.completed_at`, actor and per-unit identity/condition are server requirements for restock; DOM action is disabled before them. Negative browser test invokes handler directly and expects rejection/no inventory delta.
4. **Duplicate actions:** every visible control in a changed zone declares `data-action-intent`. For each zone+intent count must be ≤1. The required intents `open-fbs-workspace`, `create-mp-shipment`, `confirm-product-mapping`, `save-ozon-credentials`, `handover`, `return-restock` equal exactly 1 when available. Synonymous labels do not bypass this identity gate.
5. **Geometry:** measure viewport/body/main/table/dialog with `getBoundingClientRect`, `scrollWidth`, `clientWidth`, `scrollHeight`, `clientHeight`; compare the fields present in `BASELINE_GEOMETRY.json` with `actual ≤ baseline` for overflow/size and exact viewport. Existing catalog/settings/FBO narrow overflow may not increase. FBS queue narrow target body≤433.
6. **WB regression:** without fixture query and with marketplace WB, replay baseline click traces and compare visible text/action-intents, enabled states, stage transitions, request method/path/payload snapshots and numeric geometry. Shared code cannot ship if any characterization differs.

### 14.1 Zero-network harness and all fixture URLs

Fixture is an injected data/command adapter **before existing screen effects schedule**, not a separate component tree. It supplies the same view models to the same render and implements every click as a local deterministic reducer.

Enumerated URLs; no other fixture URL is allowed:

1. `/app/ff/fbs?ozonFixture=fbs-main`
2. `/app/ff/fbs?ozonFixture=fbs-auto-pass`
3. `/app/ff/mp-shipments?ozonFixture=fbo-main`
4. `/app/ff/reception?ozonFixture=return-main`
5. `/app/ff/products?ozonFixture=catalog-main`
6. `/seller/settings?ozonFixture=settings-main`

Deterministic Playwright harness:

1. Bootstrap the authenticated static application shell outside fixture acceptance.
2. Install `page.on('request', failAndRecord)` and `page.route('**/*', route => { record(route.request()); route.abort('blockedbyclient') })` **before fixture mount**.
3. Mount an enumerated fixture URL through `history.pushState` + `PopStateEvent`; this avoids allowing a navigation request after the counter is armed. The existing router mounts the fixture-backed same screen.
4. From that mount through every enumerated click below, **any** observed request of any resource type fails the test; final counter must equal zero. Aborting a request does not turn it into success. No allowlist exists.
5. Assert the initial render and all post-click states. Unhandled command, console error or rejected promise fails.

Clicks from initial fixture mount:

- `fbs-main`: in `Маркетплейс` choose `Ozon` → check posting → click `Начать сборку` → in `Состав` click `Начать сборку` → fill current location scanner with `A-01-01` and press `Enter` → fill current product scanner with line-A barcode and press `Enter` twice → fill it with line-B barcode and press `Enter` once → click tab `Упаковка и маркировка` → assert `Ozon отклонил код: …` → click `Исправить код` → fill `Код маркировки` and press `Enter` → click `Упаковать 2 из 3` → click `Упаковать оставшуюся единицу` → click tab `Короба` → click `Проверить состояние` → click `Подтвердить, что этикетка наклеена` → click `Передать поштучно`.
- `fbs-auto-pass`: check posting → click `Начать сборку` → in `Состав` click `Начать сборку` → assert read-only tab `Подбор`, visible reason, picked=plan=3 and packed=0 → click tab `Упаковка и маркировка`.
- `fbo-main`: in `Маркетплейс` choose `Ozon` → click `Создать отгрузку на МП` → in `Схема поставки` choose `Прямая` → in `Склад Ozon` choose the fixture destination → fill `Интервал приёмки` → click `Добавить товары` → select fixture product and quantity 3 → click `Добавить в отгрузку` → click `Утвердить` → click `Проверить состояние` → click tab `Подбор` → fill the current barcode scanner and press `Enter` three times → click tab `Упаковка` → expand `Короба` → set `Кол-во коробов` to 1 → click `Создать короб` → click the existing box action `Добавить товары` → choose all three units → click `Добавить в короб` → click `Связать с грузоместом Ozon` → click `Добавить в транспортное грузоместо` → click `Подготовить этикетку` → click `Проверить состояние` → click `Подтвердить, что этикетка наклеена` → click `Завершить` → assert `Передано со склада`, then fixture acceptance `План 3 · принято 2 · отклонено 1`.
- `return-main`: click the Ozon return row → click `Начать приёмку` → fill current `Принято` control with 1 → assert `Вернуть в продажу` disabled → choose `Товар совпадает` → choose `Без повреждений` → click `Завершить осмотр` → click `Вернуть в продажу` → assert disposition selected, request counter 0 and fixture available-stock value unchanged.
- `catalog-main`: click `Связь с Ozon` in the existing row → click `Отклонить вариант` for the ambiguous barcode → choose the exact Ozon account/offer radio → click `Подтвердить связь` → click existing `Создать товар` → assert baseline WMS fields and one explanatory sentence → click `Закрыть`.
- `settings-main`: click `Добавить подключение` → fill only `API-ключ` → click `Сохранить` → assert `Укажите Client-Id и API-ключ` → fill `Client-Id` → click `Сохранить` → click `Проверить подключение` → click `Синхронизировать товары и справочники` → assert partial message and preserved last-success values → click WB `Заменить ключ` → assert baseline WB dialog → click `Отмена`.

## 15. Required named side-by-side screenshots

Target folder: `docs/evidence/ozon-module-20260824/semantic-reuse-acceptance/`. Each pair uses identical role, viewport, scroll position and open state; baseline source is copied without modification and Ozon target is new.

| Surface/state | Desktop baseline → Ozon | Narrow baseline → Ozon |
|---|---|---|
| FBS queue | `01-fbs-queue-desktop-baseline.png` (`02-fbs-queue-desktop.png`) → `01-fbs-queue-desktop-ozon.png` | `02-fbs-queue-narrow-baseline.png` (`01-fbs-queue.png`) → `02-fbs-queue-narrow-ozon.png` |
| FBS Состав | `03-fbs-composition-desktop-baseline.png` (`12-...`) → `03-fbs-composition-desktop-ozon.png` | `04-fbs-composition-narrow-baseline.png` (fresh same baseline state) → `04-fbs-composition-narrow-ozon.png` |
| FBS Подбор | `05-fbs-picking-desktop-baseline.png` (`14-...`) → `05-fbs-picking-desktop-ozon.png` | `06-fbs-picking-narrow-baseline.png` (`15-...`) → `06-fbs-picking-narrow-ozon.png` |
| FBS Упаковка | `07-fbs-packing-desktop-baseline.png` (`13-...`) → `07-fbs-packing-desktop-ozon.png` | `08-fbs-packing-narrow-baseline.png` (fresh same baseline state) → `08-fbs-packing-narrow-ozon.png` |
| FBS Короба | `09-fbs-boxes-desktop-baseline.png` (fresh baseline state) → `09-fbs-boxes-desktop-ozon.png` | `10-fbs-boxes-narrow-baseline.png` (fresh baseline state) → `10-fbs-boxes-narrow-ozon.png` |
| MP shipments create/list | `11-mp-list-desktop-baseline.png` (`03-...`) → `11-mp-list-desktop-ozon.png` | `12-mp-list-narrow-baseline.png` (fresh baseline state) → `12-mp-list-narrow-ozon.png` |
| FBO document | `13-fbo-document-desktop-baseline.png` (`04-...`) → `13-fbo-document-desktop-ozon.png` | `14-fbo-document-narrow-baseline.png` (`16-...`) → `14-fbo-document-narrow-ozon.png` |
| Reception queue | `15-reception-queue-desktop-baseline.png` (`06-...`) → `15-reception-queue-desktop-ozon.png` | `16-reception-queue-narrow-baseline.png` (fresh baseline state) → `16-reception-queue-narrow-ozon.png` |
| Return card | `17-return-card-desktop-baseline.png` (`08-...`) → `17-return-card-desktop-ozon.png` | `18-return-card-narrow-baseline.png` (`17-...`) → `18-return-card-narrow-ozon.png` |
| Catalog table | `19-catalog-desktop-baseline.png` (`09-...`) → `19-catalog-desktop-ozon.png` | `20-catalog-narrow-baseline.png` (`18-...`) → `20-catalog-narrow-ozon.png` |
| Catalog create dialog | `21-catalog-dialog-desktop-baseline.png` (`10-...`) → `21-catalog-dialog-desktop-ozon.png` | `22-catalog-dialog-narrow-baseline.png` (fresh baseline state) → `22-catalog-dialog-narrow-ozon.png` |
| Seller settings | `23-settings-desktop-baseline.png` (`11-...`) → `23-settings-desktop-ozon.png` | `24-settings-narrow-baseline.png` (`19-...`) → `24-settings-narrow-ozon.png` |

`fresh baseline state` means a new screenshot from the unmodified baseline commit where the original nineteen did not capture that exact state. It is not permission to substitute an Ozon screenshot for baseline.

## 16. Точное задание на кликабельный React-прототип

1. Start only from `2af800d5846d351904cab050860356038b6d282e`; remove all rejected Ozon semantic branches from `309e85d6` rather than repairing their copy.
2. Change only the existing components named in §1 plus test-only local data/command adapters. Do not add application routes, screens, pages, tabs, documents, workspaces, modals or navigation.
3. Render production and fixture view models through the same current React tree. Query may choose a local adapter before effects, but may not select a replacement screen/workspace/modal.
4. Implement exactly the Russian copy, action-intents and click traces in §§3, 13, 14.1. Remove all visible rejected jargon and every WB label inside Ozon roots.
5. Keep stage counts/order exact: FBS 4; FBO 3. Make every tab operate the real current panel.
6. Use one progress selector and enforce the formulas after every reducer transition. Implement auto-pass as picked=plan with visible reason.
7. Implement per-unit return inspection state; restock handler rejects calls before inspection even if DOM is bypassed.
8. Arm the zero-request harness before fixture mount; all six URLs and every click must end with zero observed requests.
9. Add action-intent uniqueness, semantic surface AST, copy, progress, return, geometry and WB regression tests. Negative self-tests must prove the gate rejects: early full-screen return, Ozon-only modal, duplicate open actions, WB text in Ozon, forbidden jargon, packed>picked, restock-before-inspection and a single attempted request.
10. Capture all named screenshot pairs in §15. Browser reviewer records URL, role, clicks, visible states, geometry JSON, zero-request counter and WB replay. No screenshot/test is `PRODUCT_BROWSER_APPROVED` by itself.

No production code, prototype code, data, key, provider call, deploy or owner question is part of this architecture call.
