# Ozon в WMS: reuse-first архитектура после отклонения S0

**Call ID:** `09-ozon-architecture-reuse-rework`

**Дата:** 24 августа 2026 года

**Основание:** просьба владельца «Сделать модуль Ozon», исследование `docs/runs/ozon-module-20260824/01-ozon-domain-research.md` и обязательный verdict `tasks/ozon-module-20260824/S0_PRODUCT_VERDICT.md`

**Статус:** архитектурная коррекция до нового прототипа; production-код и prototype-код этим документом не разрешены
**Историческое свидетельство:** prototype commit `937982c46f80b7e13642cc939a4c027e9b808db5` отклонён. Его browser acceptance прерван и не возобновляется.

## 1. Решение

Ozon не становится отдельным UI-модулем. Он становится ещё одним adapter существующих складских процессов. FBS остаётся на `/app/ff/fbs` и использует нынешние очередь и modal-workspace; Ozon FBO остаётся документом «Отгрузка на МП» на `/app/ff/mp-shipments`; каталог Ozon связывается с WMS-товарами внутри `/app/ff/products`; кабинет подключается внутри `/seller/settings`; возврат создаёт обычную заявку `InboundIntakeRequest(operation_type="return")` и проходит текущую приёмку, сортировку и seller documents.

Это не означает, что Ozon притворяется Wildberries. В backend сохраняются Ozon-сущности `posting → lines → units/exemplars → packages`, FBO `supply order → cargo → TGM → acceptance act`, сырые статусы, возможности и асинхронные операции. Adapter проецирует их в общий операторский контракт существующих экранов. Поэтому оператор не получает второй складской процесс, а Ozon-семантика не стирается.

Целевой UI содержит **ноль новых top-level routes, экранов, отдельных workspaces и Ozon-разделов**. Все `/app/ff/ozon/*`, пункт навигации `Ozon`, отдельные Ozon FBS/FBO/catalog/connection/returns экраны и прежний prototype contract исключены из target design.

## 2. Факты, решения и неизвестное

### Подтверждено исследованием и кодом

- Ozon FBS posting содержит `products[]`, количества и может делиться на packages/postings. Текущий `FbsOrder` хранит один `product_id` и WB-specific identifiers, поэтому прямое помещение Ozon в эту таблицу потеряет смысл строк и количеств.
- Ozon package label создаётся асинхронно; FBO draft, supply, cargo, labels и часть act-операций также завершаются через status/readback. HTTP 200 не доказывает бизнес-успех.
- FBS может сдаваться поштучно по barcode posting; общая carriage не является обязательным родителем каждого posting.
- Push может запаздывать. Polling и entity readback остаются механизмами сходимости.
- `/app/ff/fbs` уже содержит очередь, selection, текущий `FfFbsSupplyWorkspace`, подбор из ячеек, маркировку, упаковку, короба, печать и передачу.
- `/app/ff/mp-shipments` уже содержит документ отгрузки на маркетплейс, строки, резерв, подбор, packaging task, физические короба и проведение.
- `InboundIntakeRequest` уже поддерживает `operation_type="return"`, а физическая приёмка меняет остатки только отдельными действиями.
- `SellerSettingsScreen` уже является местом marketplace credentials, но текущая заготовка `ozon` в marking credentials не реализует Seller API identity `Client-Id + Api-Key`, roles или expiry.
- `FfProductsCatalogScreen` уже является общим каталогом товара и содержит действие-зону строки; отдельный Ozon-каталог дублирует пользовательскую работу.

### Решено этой архитектурой

- `MarketplaceAccount` является account-scoped identity. Все внешние IDs, mappings, checkpoints, operations и assets включают `marketplace_account_id`.
- Ozon-каталог в этой программе import-only. Публикации карточек и записи остатков нет даже как выключенной кнопки.
- Ozon provider-native data хранится additively; существующие WB-таблицы не переименовываются и не мигрируют в первой программе slices.
- UI читает provider-neutral `FbsWorkItemView` и `FbsWorkspaceView`. WB adapter формирует тот же наблюдаемый результат, который формирует текущий код; Ozon adapter добавляет только capabilities и conditional fields.
- Ozon FBO расширяет `MarketplaceUnloadRequest`: WMS document остаётся authority для локального плана, резерва, подбора, packaging task и коробов; внешние Ozon supply/cargo/TGM/act children не заменяют физические WMS-сущности.
- Ozon return создаёт существующую inbound-заявку. Внешний return status не увеличивает доступный остаток; до решения осмотра товар остаётся в карантинной ячейке.
- Любое Ozon mutating action разрешается только при одновременном наличии discovered capability, project allowlist и entity `available_actions`. Неизвестное выключает конкретное действие, а не весь процесс.

### Неизвестное не превращается в выдумку

- Реальный auth mode, roles и expiry конкретного account неизвестны без полной credential pair. Safe fallback: `pending_credentials`, без внешнего вызова.
- Route modes, cargo/TGM rules, labels и available actions зависят от account и сущности. Safe fallback: read-only discovery/readback; локальная работа сохраняется, внешняя mutation блокируется.
- Универсальный idempotency header для всех Ozon mutations не подтверждён. Safe fallback: operation ledger + readback before retry.
- Форматы/размеры отдельных assets не зафиксированы. Safe fallback: binary pass-through без resize, версия/checksum и обязательный print sample до включения действия.
- Политика решения по повреждённым returns не дана. Safe fallback: карантин и `needs_shift_lead`; auto-restock запрещён.

## 3. Primary user и его работа

**Primary user — оператор фулфилмент-склада.** Его работа — вовремя найти нужные единицы в WMS, взять их из доказанной ячейки, выполнить требования конкретного marketplace posting/supply, упаковать физически и внешне корректно, напечатать актуальную этикетку, передать груз и не показать ложное завершение до подтверждения маркетплейса.

Каждый заметный элемент target process существует ради этой работы:

- Компактный marketplace marker внутри существующей строки нужен, чтобы оператор не напечатал WB-стикер для Ozon и не выбрал несовместимый способ сдачи. Отдельная колонка для него не нужна.
- Для Ozon строка показывает `N товаров · M единиц`, потому что оператор подбирает количество по product line, а не один абстрактный «заказ».
- Раскрытие состава внутри текущей строки нужно до selection: shortage одной Ozon line должен блокировать только честно показанный posting, а не обнаруживаться после начала сборки.
- Required fields показываются только для конкретной единицы, потому что KIZ, IMEI, GTIN, weight и country не являются одной общей «маркировкой» и не должны создавать лишние сканы.
- `Локально принято` и `Ozon подтвердил` видны отдельно, потому что оператор может исправить rejected exemplar до необратимого ship.
- WMS box, Ozon package, FBO cargo и TGM видны как разные связи внутри текущей упаковочной зоны, потому что один физический короб не доказывает правильную внешнюю container hierarchy.
- `Операция выполняется` остаётся рядом с кнопкой, которая её запустила, потому что смене нужен truthful next action — дождаться/readback, а не повторить mutation и создать дубль.
- Возврат ведёт в карантин и осмотр в текущей приёмке, потому что marketplace status не доказывает, что физическая единица годна к продаже.

Secondary users:

- **Seller admin** подключает marketplace account в `/seller/settings`, видит identity, roles, expiry и sync health. Ему не нужны кнопки складской упаковки.
- **FF admin** подтверждает account-scoped product mapping в `/app/ff/products` и разбирает unmapped/blocker states.
- **Планировщик/руководитель смены** ведёт Ozon FBO в текущем документе MP shipment, выбирает доступный route/timeslot и разбирает uncertain operation/acceptance discrepancy.
- **Сотрудник приёмки** принимает Ozon return в существующем inbound flow и фиксирует disposition после физического осмотра.

## 4. Жёсткая reuse-map процесса

Машинный источник — `tasks/ozon-module-20260824/REUSE_MAP.json`. Ниже человеческое объяснение той же границы.

| Требование | Существующая поверхность | Минимальное изменение | Доказанная Ozon-необходимость |
|---|---|---|---|
| FBS очередь | `/app/ff/fbs`, `FfFbsOrdersScreen` | marketplace filter/marker, multi-line summary, capability-derived blockers; без новой колонки и вкладки | Ozon posting имеет несколько lines/units и иной handover |
| FBS рабочее место | Тот же modal `FfFbsSupplyWorkspace` | provider-neutral labels/actions; quantities, exemplar states, package composition и async label внутри текущих четырёх стадий | `FbsOrder=1 product` и WB sticker/trbx не выражают Ozon package |
| FBO | `/app/ff/mp-shipments`, текущий `MarketplaceUnloadRequest` modal | marketplace/account/route fields в header, Ozon cargo/TGM/labels в существующей «Упаковке», acceptance inline после ship | Ozon supply/cargo/TGM/act — внешние children локальной отгрузки |
| Каталог | `/app/ff/products`, product row/action zone | marketplace mapping status и confirm dialog в текущей строке; sync запускается из settings | Ozon offer_id/product_id/sku account-scoped и не помещаются в `Product.wb_*` |
| Подключение | `/seller/settings`, существующий credentials card area | отдельная Ozon account card рядом с неизменённой WB card | Ozon требует Client-Id + Api-Key или OAuth, roles и expiry |
| Возвраты | `/app/ff/reception`, `/app/ff/sorting`, `/seller/documents`, `/seller/inbound/:requestId` | imported return source/identifiers, quarantine scan и conditional inspection block внутри существующей карточки | Физическая единица может быть повреждена/подменена; auto-restock опасен |
| Асинхронные состояния | Та кнопка/зона существующего документа, где действие запущено | `pending / uncertain / failed / confirmed` и safe readback action inline | Ozon operation status может содержать ошибку после HTTP success |
| Акты/расхождения | Текущий MP shipment document и существующая discrepancy semantics | Ozon acceptance summary/act asset после ship; строковые discrepancies без нового документа | `shipped`, `accepted` и `act agreed` — разные факты |

Удаляется из target design:

- `/app/ff/ozon`, `/app/ff/ozon/fbs`, `/app/ff/ozon/fbs/:postingId`;
- `/app/ff/ozon/fbo`, `/app/ff/ozon/fbo/:supplyOrderId`;
- `/app/ff/ozon/catalog`, `/app/ff/ozon/connection`;
- `/app/ff/ozon/returns`, `/app/ff/ozon/returns/:id`;
- `nav-ff-ozon`, отдельный Ozon dashboard, Ozon FBS/FBO/returns workspaces и их parallel navigation.

## 5. Нормальный процесс end to end

### 5.1 Подключение и каталог

1. Seller admin открывает существующие настройки `/seller/settings`. В card area «Подключения маркетплейсов» WB card остаётся визуально и функционально прежней; рядом появляется Ozon account card для выбранного seller.
2. Для direct auth форма требует оба поля `Client-Id` и `Api-Key`. Неполная пара сохраняет только локальный draft и не вызывает Ozon. Это защищает администратора от ложного «подключено» и от попытки угадать account identity.
3. После `Проверить подключение` WMS читает seller info/roles, сравнивает external identity и показывает account state, roles, expiry и last successful discovery в той же card. Эти данные нужны администратору, чтобы понять, почему импорт или операция недоступны, а не читать технический лог.
4. `Синхронизировать товары и справочники` запускает account-scoped background job. Card показывает last confirmed data, progress и partial error; при 429/timeout данные не исчезают.
5. FF admin открывает существующий `/app/ff/products`. В текущей action zone строки видит `WB связан`, `Ozon не связан` или конфликт. Диалог связи показывает offer_id/product_id/sku/barcodes и причину кандидата. Явное подтверждение нужно, потому что одинаковый barcode у разных accounts не доказывает ownership.
6. External warehouses, delivery methods, clusters и return points хранятся account-scoped. В Ozon account card текущих настроек компактный binding block связывает FBS seller warehouse с WMS warehouse и задаёт quarantine location для returns, потому что без этих двух физических назначений очередь и приёмка не могут безопасно начать работу. Переменный FBS delivery method показывается в текущем selection/preflight, а FBO destination/route выбирается в MP shipment header. Общий отдельный topology screen или tab не создаётся.

### 5.2 FBS в существующей очереди и workspace

1. Push ускоряет intake, polling `/v4/posting/fbs/unfulfilled/list` восстанавливает пропуски. После event WMS делает detail readback и атомарно upsert posting, lines, requirements и raw external state.
2. Ozon adapter создаёт один `FbsWorkItemView` на posting, не на line. В `Товар` существующей строки показываются первые line items и `ещё N`; рядом totals `lines_count`/`units_count`. Это сохраняет один внешний posting как одну работу и не теряет количество.
3. До selection сервис проверяет account, mapping каждой line, warehouse binding, inventory availability и current `available_actions`. Blocker показывается в той же строке рядом с disabled selection, чтобы оператор не начал физическую работу, которую нельзя завершить.
4. Selection не смешивает marketplace accounts. Для WB существующее действие и copy остаются прежними. Для Ozon тот же selection bar запускает `Начать сборку`; backend создаёт локальный Ozon work batch, а не внешнюю carriage. Это даёт текущему modal-workspace стабильный ID, но не навязывает Ozon внешнюю поставку.
5. В существующей стадии `Состав` Ozon posting разворачивается в lines и quantities. Никакой новой вкладки нет. Оператор сверяет полный объём перед подбором.
6. В `Подбор` оператор сканирует ячейку, затем product barcode. Adapter находит line внутри posting и увеличивает picked quantity; excess/wrong seller/wrong line отклоняются до inventory mutation. Одна готовая line остаётся видимой, даже если соседняя line в shortage.
7. В `Упаковка и маркировка` для каждой unit показываются только required exemplar fields. Локальный scan, отправка в Ozon, external validation и correction — отдельные состояния одной текущей строки. `Rejected` не переводит всю упаковку в completed.
8. В той же стадии физическая `PackagingTask` остаётся authority работы с остатком. Additive Ozon package composition связывает package с line quantities. Partial package уменьшает remaining quantity и создаёт/обновляет external posting только после readback; исходный posting не считается целиком packed автоматически.
9. Асинхронная package label отображается в текущей print zone как `Запрашивается`, `Готова`, `Ошибка`. Печать доступна только для ready/current asset; superseded version нельзя подтвердить как нанесённую.
10. В текущей стадии `Короба` WMS box остаётся физической тарой. Для Ozon рядом с конкретным box/package видна связь с posting/package label. WB trbx controls не рендерятся для Ozon; это conditional replacement в той же zone, не новый workspace.
11. Кнопка handover в этой же стадии строится из capability. One-by-one подтверждает фактическую передачу по posting barcode; carriage появляется только когда она разрешена и нужна для выбранного delivery method. Manual portal fallback не меняет внешний status: после ручной работы WMS делает readback.
12. `handed_over_wms`, Ozon `delivering/delivered/cancelled/arbitration` и local reversal хранятся отдельно. Отмена после pick создаёт возврат единиц через текущий scan-to-location path; без проведённого movement резерв/остаток не «исправляется» статусом.

### 5.3 FBO в существующем документе «Отгрузка на МП»

1. Планировщик остаётся на `/app/ff/mp-shipments` и создаёт тот же локальный document. В существующей create zone появляется marketplace selector, потому что route/destination и external actions зависят от площадки. Default/fixture WB должен воспроизводить текущую кнопку и дальнейший процесс без отличий.
2. Для Ozon в header созданного draft выбираются account, direct/crossdock/multi-cluster из discovered capabilities, destination и timeslot. Эти поля стоят здесь, потому что они определяют, куда физически готовится этот документ; отдельный wizard или FBO screen только разорвёт связь с WMS plan.
3. Вкладка `Товары` остаётся планом состава. Account-scoped mapping blocks submit строки, но локальный draft можно сохранить. Ozon supply-order creation создаёт operation intent; document показывает pending/uncertain inline и не становится confirmed до readback.
4. `Подбор` использует существующий scan location/product и allocations. Ozon не получает отдельный scanner flow, потому что физическое списание из WMS одинаково для marketplace shipments.
5. `Упаковка` использует существующую PackagingTask и WMS boxes. После текущего блока коробов conditional section `Грузоместа Ozon` показывает правила, cargo и TGM hierarchy. Она нужна не «для удобства», а чтобы оператор связал уже закрытый физический короб с обязательным внешним cargo/TGM до печати.
6. Cargo/TGM create/delete и labels имеют inline operation state. Retry доступен только после readback. Partial failure не стирает готовые cargo; проблемная строка остаётся с конкретной причиной.
7. В document footer текущая `Отгрузить` сначала проверяет completed packaging, line distribution, cargo/TGM rules, current labels и fresh external state. Local `shipped_at` и Ozon handover/acceptance не сливаются.
8. После ship тот же document показывает acceptance summary по lines: planned, accepted, rejected и reason. Act PDF и capability-dependent `Согласовать акт` живут здесь, потому что руководитель сверяет результат именно этой отгрузки. Новая вкладка/документ не создаётся.
9. Если beta act capability отсутствует, document остаётся read-only и показывает ручную проверку в кабинете плюс `Проверить состояние`; WMS не подделывает согласование.

### 5.4 Returns в существующей приёмке

1. Poll `/v1/returns/list` создаёт или обновляет external return record и связывает его с account, FBS posting/FBO supply и product mapping. Duplicate events не создают второй inbound document.
2. Когда возврат ожидается физически, WMS idempotently создаёт `InboundIntakeRequest(operation_type="return")`. Он появляется в существующей `/app/ff/reception` и seller `/seller/documents`; отдельной Ozon queue нет.
3. В существующей inbound card показываются source `Ozon`, return/posting identifier, masked exemplar tail и expected quantity. Эти identifiers нужны сотруднику, чтобы не принять похожий товар к чужому seller/account.
4. При скане сотрудник выбирает/сканирует карантинную location. Если quarantine binding отсутствует, фактическую единицу можно зафиксировать как received, но `post/restock` блокируется. Это безопаснее догадки о годности.
5. Conditional block `Осмотр возврата Ozon` в той же line фиксирует identity match, packaging/condition и disposition: `restock`, `keep_quarantine`, `defect`, `return_to_seller`. Default не выбран, потому что решение должно следовать физическому осмотру.
6. Только `restock` после подтверждённого осмотра проводит existing inbound inventory movement в доступную location. Остальные outcomes оставляют товар недоступным или запускают существующую ручную складскую работу; внешний status сам остаток не меняет.

## 6. Ошибки и частичные состояния

| Состояние | Что видит пользователь в текущей поверхности | Разрешённое восстановление |
|---|---|---|
| Нет Client-Id или Api-Key | Ozon card `Не заполнены данные`; sync/actions disabled | Заполнить пару; внешних calls до этого нет |
| Identity mismatch | Account card показывает expected/observed identity без секретов | Shift lead/admin исправляет выбранный seller/account; автоматического relink нет |
| Role/capability отсутствует | Конкретная action disabled с business reason | Manual portal fallback + readback либо capability остаётся off |
| Частичная pagination/429 | Last confirmed rows остаются; card показывает partial sync и cursor resource | Background job продолжает с committed checkpoint и backoff |
| Unknown external status | Строка остаётся в текущей вкладке как `Статус уточняется`; irreversible actions blocked | Detail readback; raw value сохраняется для аудита |
| Multi-line shortage | Posting виден, готовые lines и shortage line различимы | Довнести остаток, remap или отменить работу; готовность не подделывается |
| Exemplar rejected | Unit line показывает Ozon reason и correction до ship | Исправить только эту unit и revalidate |
| Ship/cargo/label timeout | Inline `Результат не подтверждён`; повтор disabled | Readback operation/entity, затем resume/retry по ledger |
| Label pending/failed | Print zone не открывает старый asset как current | Poll task; retry после confirmed failure; старый asset superseded |
| Posting cancelled after pick | Current FBS workspace переводит единицы в reversal | Scan target location/quarantine и провести compensating movement |
| FBO cargo partial error | Готовые cargo сохранены, проблемный cargo отмечен | Исправить rules/composition только проблемного cargo и readback |
| Act discrepancy | Same MP document показывает planned/accepted/rejected | Shift lead принимает решение/ручной fallback; auto-accept отсутствует |
| Return unmatched | Existing return inbound visible as `Не сопоставлен`, post disabled | Admin confirms mapping; физическая единица остаётся в quarantine |
| Push delayed/duplicate/out-of-order | Пользователь не видит дублей; freshness остаётся честной | Poll authority + dedupe + entity version/readback |

## 7. Границы ответственности

### WMS отвечает за

- tenant/seller/account isolation, roles и audit;
- account-scoped mappings и bindings;
- локальный резерв, ячейки, scans, PackagingTask, WMS boxes и inventory movements;
- truthful projection внешнего состояния и допустимого next action;
- operation ledger, checkpoints, dedupe, retry/readback и versioned assets;
- quarantine и запрет auto-restock returns;
- сохранение WB observable behavior.

### Ozon отвечает за

- identity/roles/capabilities account;
- posting/supply/cargo/TGM lifecycle, restrictions, `available_actions` и cancellation;
- external validation exemplars;
- выдачу package/cargo/TGM labels, barcodes, acts и acceptance result;
- rate limits, API schema and operation results.

### Ручные действия остаются ручными

- физический scan location/product/unit;
- упаковка, нанесение label и передача в пункт/перевозчику;
- действие в Ozon cabinet, когда API capability отсутствует;
- print sample до включения неизвестного формата;
- осмотр возврата и решение по damage/mismatch;
- разбор arbitration/acceptance discrepancy руководителем смены.

WMS не ставит `delivered`, `accepted`, `act_agreed` или `restocked` только потому, что оператор сообщил о ручном действии. Он фиксирует manual evidence отдельно и ждёт внешний readback или проведённое inventory movement.

## 8. Варианты и цена

### Вариант A — разложить Ozon posting в текущие `FbsOrder`

Каждая line или unit становится псевдо-заказом WB-типа. Цена кажется низкой: 2–4 недели backend/UI. Реальная цена высока: posting status/label дублируются, quantities и partial package распадаются, один mutation может быть повторён по нескольким rows, `wb_supply_id/trbx` начинают означать другое. Этот вариант стирает Ozon-семантику и создаёт риск WB regression. **Отклонён.**

### Вариант B — additive Ozon aggregates + adapter-backed projection в текущий FBS UI

Provider-native Ozon tables хранят lines/units/packages, а `FbsWorkItemView`/`FbsWorkspaceView` проецируют их в существующую очередь и modal-workspace. WB adapter читает текущие models без миграции. FBO и returns расширяют существующие documents. Оценка: 8–12 вертикальных slices, примерно 12–18 инженерных недель с emulator, миграциями, print gates и browser acceptance. UI-цена ограничена пятью существующими зонами. **Выбран.**

### Вариант C — сразу мигрировать WB и Ozon на единый canonical marketplace domain

Это чище на длинном горизонте, но требует backfill `FbsOrder/FbsSupply/FbsTrbx`, переключения всех jobs/actions и одновременной регрессии всего WB lifecycle. Оценка: 20–30+ инженерных недель и высокий release risk. **Отложен.** Общий projection contract из варианта B создаёт seam для будущей миграции без принуждения сейчас.

### Почему B — наименьший безопасный

Он добавляет данные только там, где Ozon доказанно сложнее текущего WB order, и переиспользует каждый физический процесс/экран. Он не делает WB migration prerequisite, не создаёт parallel UI и не превращает Ozon posting в ложный набор однотоварных заказов.

## 9. Данные и инварианты

Названия ниже — target model contract, не production patch.

### 9.1 Общий integration spine

- `marketplace_accounts`: `id`, `tenant_id`, `seller_id`, `marketplace`, `auth_mode`, encrypted credential references, `external_identity`, `status`, roles/capabilities JSON, expiry, discovery timestamps. Unique external identity scoped by marketplace; secret values никогда не возвращаются.
- `marketplace_product_mappings`: account, external `offer_id/product_id/sku`, `product_id`, status, source, confirmed_by/at, raw snapshot. Unique external key inside account.
- `marketplace_nodes` и `marketplace_node_bindings`: account/resource kind/external id/raw snapshot; binding к WMS warehouse и optional quarantine location. FBS warehouse, FBO destination, cluster, delivery method и return point не сливаются в одно поле.
- `marketplace_sync_checkpoints`: account + resource + API version + filter fingerprint, committed cursor/last_id/window and last success.
- `marketplace_event_inbox`: account + external event id/type/version/hash, received/processed state; duplicates idempotent.
- `marketplace_operations`: account, entity kind/id, action, immutable intent fingerprint, external operation/task id, `pending|uncertain|confirmed|failed|manual_required`, request metadata sans secrets, last readback/error and actor. Unique active intent per entity/action/fingerprint.
- `marketplace_assets`: account, entity kind/id, kind, source/version/task id, status, storage path, checksum, dimensions/content type, superseded/applied audit.

Это новые backend seams, не новые UI surfaces. Existing `BackgroundJob`, encrypted secret service и print storage patterns переиспользуются, но WB-only fields не переименовываются в-place.

### 9.2 Ozon FBS aggregate

- `ozon_fbs_postings`: account, posting_number, WMS warehouse, external status/substatus/actions/raw, deadlines/delivery method, local workflow state, cancellation, sync version.
- `ozon_fbs_posting_lines`: posting, stable external line key, offer/product/sku snapshot, mapped WMS product, ordered/picked/packed quantities and requirements.
- `ozon_fbs_units`: line + ordinal, required fields, masked identifiers and local/external validation states. Full sensitive codes use encrypted/restricted storage and sanitized audit.
- `ozon_fbs_packages`: posting/current external posting reference, package ordinal, status, restrictions version, label asset and supersession.
- `ozon_fbs_package_lines`: package + line + positive quantity. Invariants: sum package quantities per line cannot exceed ordered quantity; ship requires accepted required units and fresh restrictions.
- `ozon_fbs_work_batches` + membership: local grouping used only to open the existing modal-workspace for one or more compatible postings. It is not Ozon carriage/supply and never appears as a new document type or navigation entry.

`FbsWorkItemView` has provider-neutral identifiers, seller/account, warehouse/route, deadline, `lines[]`, quantities, product preview, selection blockers, local/external status and capabilities. For WB, current one product becomes one line/one unit and existing copy/actions stay unchanged. For Ozon, posting stays one item with many lines.

`FbsWorkspaceView` keeps the existing visual stages `composition`, `picking`, `packing`, `boxes`. Provider-specific zones are conditional payloads: `exemplar_requirements`, `packages`, `label_assets`, `handover_modes`, while WB keeps `wb_supply/trbx/supply_qr` fields.

### 9.3 Ozon FBO extension

`MarketplaceUnloadRequest` receives additive `marketplace_account_id`, `marketplace`, external process state/reference and route/timeslot snapshot. Existing lines, reservations, pick allocations, PackagingTask and boxes remain WMS authority.

Children:

- `ozon_fbo_supply_links`: document → supply order/supply, route type, destination, timeslot, external/local states;
- `ozon_fbo_cargoes`: supply link, external cargo id, rules version, state;
- `ozon_fbo_cargo_box_links`: cargo ↔ existing `MarketplaceUnloadBox` with quantities/validation;
- `ozon_fbo_transport_cargoes` and membership: TGM hierarchy separate from WMS box/cargo;
- acceptance line snapshots and act state/asset under the same document.

No `OzonFboWorkspace`, no separate FBO document and no new route.

### 9.4 Returns extension

- `marketplace_returns`: account, external return id/type/status, source posting/supply, mapped product/unit, quantities, return point, raw snapshot and last sync.
- link to one existing `InboundIntakeRequest(operation_type="return")` with unique constraint for idempotency;
- `marketplace_return_inspections`: inbound line/unit, identity match, condition, disposition, actor/time and notes/assets where approved later.

Inventory invariant: external return import and physical received scan do not increase available stock. Only the existing posted inbound movement after `restock` can do that.

### 9.5 Migration order

1. Integration spine and account isolation; no UI switch.
2. Catalog/node snapshots and mappings; read-only jobs.
3. Ozon FBS aggregate and projection behind disabled capability.
4. Ozon FBO links/children on existing MP document.
5. Return links/inspection on existing inbound document.
6. Enable provider by seller/account after fixtures, regression and browser gate.

No existing WB column becomes nullable/renamed for Ozon, no backfill of WB orders is required, and rollback disables Ozon capabilities without deleting operator evidence.

## 10. Backend boundaries and reusable WMS parts

### Reuse unchanged or behind a narrow facade

- `Tenant`, `Seller`, `Product`, `Warehouse`, `StorageLocation` and inventory services;
- `PackagingTask`, its lines/events and existing MP unload integration;
- `MarketplaceUnloadRequest`, lines, reservations, pick allocations and boxes;
- `InboundIntakeRequest`, box/cargo place, receive/verify/post/distribute flow;
- `BackgroundJob` shell, job polling and current scheduler pattern;
- FBS worklist/workspace, picking, packaging and print storage patterns;
- MUI screens and current routes listed in the reuse map;
- role/effective seller checks and audit conventions.

### Do not reuse as generic truth

- `FbsOrder.wb_*`, `FbsSupply.wb_supply_id`, `FbsTrbx`, WB status maps and WB stock publisher;
- `Product.wb_*` as Ozon mapping;
- one `mp_api_key` in marking credentials as Seller API account identity;
- WB sticker/trbx/supply QR taxonomy for Ozon package/cargo/TGM assets;
- one universal pagination or retry implementation.

### Adapter contract

`MarketplaceAdapter` exposes typed discovery/catalog/nodes and operation primitives. `FbsWorkflowAdapter` exposes projection, preflight, exemplar, package, label, handover and readback. `MarketplaceShipmentAdapter` exposes route/draft/timeslot/supply/cargo/TGM/label/act operations. Adapters return normalized capability/action results plus raw sanitized snapshots; they do not mutate inventory directly.

WB adapter wraps current services and must be characterized before shared frontend switching. Ozon adapter is the only place with Ozon endpoint/version knowledge. Business services own DB transactions, ledger and inventory invariants.

## 11. WMS API evolution

The API changes are additive facades for existing routes, not new operator surfaces.

### Accounts and catalog

- `/integrations/marketplaces/self/accounts` list/create/patch selected seller accounts; existing `/integrations/wildberries/*` remains valid for WB compatibility.
- `/integrations/marketplaces/self/accounts/{id}/discover` starts read-only discovery job.
- `/integrations/marketplaces/self/accounts/{id}/sync` starts typed resource sync.
- `/products/ff-catalog` adds `marketplace_mappings[]`; current fields remain.
- `/products/{product_id}/marketplace-mappings` confirms/unlinks account-scoped mapping with role checks.

### FBS facade on the existing UI path

- `GET /operations/fbs-orders/worklist` gains optional `marketplace`/account filters and additive generic fields. Omitted filters and WB-only data preserve current response behavior.
- `GET /operations/fbs-supplies/worklist` returns projected work batches. Legacy WB supply identifiers remain for WB rows.
- `POST /operations/fbs-supplies/from-orders` accepts legacy `order_ids` for WB and additive homogeneous `work_item_ids`; Ozon creates a local batch only.
- Existing `/operations/fbs-supplies/{id}/workspace`, pick scans, packing/boxes, print and deliver calls dispatch through workspace provider. A provider discriminator is server-resolved from the work batch and never trusted from client seller/account input.
- Additive line/unit/package actions are under the same workspace resource; no `/ozon/fbs` API namespace is exposed to frontend.

### MP shipment/FBO

- Existing `/operations/marketplace-unload-requests` payload adds marketplace account/route fields and external operation summary.
- Child endpoints for route/timeslot/cargo/TGM/assets/acceptance live under `/operations/marketplace-unload-requests/{id}/...`, so tenant/seller/document authorization is reused.
- Existing confirm/pick/pack/ship endpoints call marketplace adapter only after local preflight and operation ledger creation.

### Returns/inbound

- Return sync is account job, not a UI route.
- Existing inbound detail adds `marketplace_return` and `inspection` conditional blocks.
- Inspection and disposition actions live under `/operations/inbound-intake-requests/{id}/lines/{line_id}/return-inspection`; posting stock still uses existing inbound post service.

### Security and status rules

- Every entity lookup scopes tenant first, then effective seller, then account.
- Client cannot choose an account belonging to another seller by ID.
- Secrets travel only in request headers to Ozon and never appear in job payload/result/logs.
- Unknown enum values are stored raw and normalized to `needs_attention`; they do not crash list endpoints.
- A mutating retry always reads operation/entity first. `Retry` without readback is not an API action.

## 12. Async operations, reconciliation and print

Operation state machine:

`intent_created → sent → pending → confirmed | failed | uncertain | manual_required`.

- `confirmed` requires operation status or authoritative entity readback matching the intent.
- Network timeout after send produces `uncertain`, not failed. The same fingerprint cannot create another active intent.
- Confirmed failure may create a new intent only after the user-visible cause changed or explicit safe retry.
- Manual portal work records actor/time/note but does not forge external success.

Sync checkpoints commit only after the entire page transaction succeeds. Push inbox deduplicates and schedules the same entity readback used by polling. Polling remains authoritative for convergence.

Asset taxonomy keeps `product_barcode`, `marking_label`, `fbs_posting_package_label`, `fbs_posting_barcode`, `fbs_carriage_act`, `fbo_cargo_label`, `fbo_tgm_label`, `fbo_acceptance_act`, `return_giveout_barcode` distinct. Each asset has source/version/checksum/status/supersession. The existing preview/print/applied interaction is reused; unsupported dimensions are pass-through only.

## 13. Точное задание на replacement clickable React prototype

### 13.1 Жёсткая граница

Prototype developer must not create a screen, route, top-level navigation item, tab, separate document type or second workspace. The obsolete `OzonModulePrototypeRoute` is not a base. Replacement prototype runs on realistic local fixtures through the **existing routes** below; a fixture flag/query may switch data, but URL topology remains current.

`App.tsx` and `AuthedAppLayout.tsx` may be touched only to remove the rejected Ozon import/routes/nav. The historical standalone prototype component is deleted, not amended. Production APIs, DB migrations and external calls are forbidden in the prototype slice.

### 13.2 `/app/ff/fbs` — bounded changed zones

1. Existing filter row: add one `Маркетплейс` select. It exists so operator selection cannot mix incompatible labels/handover; it is not a new reporting filter. WB fixture selection must show current WB labels/actions unchanged.
2. Existing worklist row: no new column. In current product/order cells, Ozon row shows marker, posting number, `2 товара · 3 шт`, first two product lines, deadline and mapping/blocker. Click/expand shows full lines inline; it does not navigate.
3. Existing selection bar/dialog: Ozon homogeneous selection uses `Начать сборку`; mixed account/marketplace selection shows one blocking reason. WB copy remains current.
4. Existing `FfFbsSupplyWorkspace` modal and four current stages only:
   - `Состав`: multi-line quantities and requirements;
   - `Подбор`: scan location/product and per-line progress;
   - `Упаковка и маркировка`: unit KIZ/IMEI states, package quantities and async label in current print zone;
   - `Короба`: WMS box ↔ Ozon package relation, posting label and capability-driven handover in the current bottom action area.
5. No Ozon dashboard, FBS route, posting details screen, extra stage/tab or parallel workspace.

Clickable fixture path: select Ozon → open posting `4829-0001-1` with two lines/three units → see one unmapped line blocker → use mapped fixture → scan location and two product barcodes → correct rejected exemplar → create partial package → label changes pending→ready → print/apply → choose discovered one-by-one handover → see `Передано WMS, Ozon ещё не подтвердил`.

### 13.3 `/app/ff/mp-shipments` — bounded changed zones

1. Existing create block: marketplace select next to seller. WB default/fixture must retain current create behavior.
2. Existing document header: Ozon-only account, route, destination, timeslot and inline async state. No wizard.
3. Existing tabs remain exactly `Товары`, `Подбор`, `Упаковка`.
4. Existing `Упаковка` zone: after WMS boxes, conditional cargo/TGM hierarchy with link, label status/print and partial error. No separate FBO tab/workspace.
5. Existing footer/post-ship body: handover preflight and acceptance/act reconciliation inline.

Clickable fixture path: create Ozon MP shipment → choose direct route and timeslot → add three lines → confirm while external operation pending → readback success → use existing pick/pack → bind two WMS boxes to two cargo inside one TGM → recover one failed label → ship → see planned 10/accepted 9/rejected 1 and manual act fallback.

### 13.4 `/app/ff/products` — bounded changed zones

1. No new catalog tab/column. Existing product action zone shows marketplace mapping summary.
2. Existing action dialog pattern opens account-scoped Ozon candidates with offer_id/product_id/sku/barcode and explicit candidate reason.
3. Search matches Ozon identifiers only when Ozon mapping data is loaded; current WB/catalog behavior remains.

Clickable fixture path: filter seller Loviana → open mapping for one product → reject ambiguous barcode candidate → confirm exact offer/SKU candidate → row shows both WB and Ozon links without changing WMS SKU.

### 13.5 `/seller/settings` — bounded changed zones

1. Existing WB card remains untouched in copy/actions. Add Ozon account card in the same settings section.
2. Direct auth dialog has Client-Id and Api-Key, masked saved state, `Проверить подключение`, roles/expiry/capability result and sync action.
3. Incomplete Fashion fixture shows `Client-Id не указан` and proves zero external call. Stock publication toggle/action is absent, not disabled.

Clickable fixture path: open incomplete account → save draft without network → complete pair with fixture values → discover identity/roles → start partial catalog sync → retain last confirmed counts on 429.

### 13.6 Existing returns/inbound routes — bounded changed zones

Routes: `/app/ff/reception`, `/app/ff/sorting`, `/seller/documents`, `/seller/inbound/:requestId`.

1. Existing queue row uses current document type `Возврат` and adds source marker/return id in existing extra text; no Ozon returns filter/tab.
2. Existing inbound detail shows conditional identifiers and quarantine location scan.
3. Existing line area shows inspection/disposition only for marketplace return. No default disposition and no stock post before restock decision.

Clickable fixture path: open unmatched Ozon return → scan return barcode → keep in quarantine because mapping missing → confirm mapping fixture → inspect damaged unit → choose `Брак` → verify available stock unchanged. Second fixture chooses `Вернуть в остаток` and posts through existing inbound action.

### 13.7 Required prototype states and evidence

Fixtures must include two sellers, simultaneous WB+Ozon for Loviana, incomplete Fashion account, multi-line/partial-package/cancelled-after-pick FBS, one-by-one and carriage capability, FBO pending/partial cargo/acceptance discrepancy, matched/unmatched/damaged returns, 429, unknown status and stale last-success data.

Product Browser Review uses a visible browser and records URL, role, clicks/scans and visible success/error/partial states for each changed route. It must explicitly re-run current WB FBS create/pick/pack/box/deliver and current WB MP shipment plan/pick/pack/ship. Verdict can only be `PRODUCT_BROWSER_APPROVED`, `PRODUCT_REWORK_REQUIRED` or `PRODUCT_BROWSER_BLOCKED`. The interrupted rejected prototype review is not evidence.

## 14. Future CI reuse scope gate

Create `scripts/ci/check_ozon_reuse_scope.py` in the implementation/prototype PR, reading `REUSE_MAP.json` and `git diff --name-status <merge-base>...HEAD`.

The gate fails when:

1. `policy != reuse_first`, JSON invalid, a visible row lacks any required field, or any `new_surface_required` is true without non-empty concrete `incompatibility_evidence` and explicit exception scope.
2. An added/touched UI file under `frontend/src/screens`, `frontend/src/pages`, `frontend/src/prototypes`, routing or layout is not matched by at least one row's `allowed_files`.
3. Diff adds a React route, navigation target, screen/page export, top-level tab, document kind or workspace not equal to a row's `existing_route`/`existing_surface`.
4. Any added route/path/navigation text matches `/ozon`, `ozon/fbs`, `ozon/fbo`, `ozon/catalog`, `ozon/connection` or `ozon/returns`.
5. `App.tsx`, `AuthedAppLayout.tsx` or the obsolete prototype are changed for anything except deletion of the rejected import/routes/nav/component.
6. A changed existing screen falls outside the `minimal_delta` and `forbidden_scope` text for its mapped requirement; PR must declare requirement IDs in `### Ozon reuse scope` and the script compares them to files.
7. A new frontend file exports a `*Screen`, `*Page`, route component, navigation config, workspace or top-level tabs. Helper/fixture components are also forbidden unless explicitly mapped and contain no route/screen registration.
8. WB characterization snapshots/e2e listed by the architecture are absent when shared FBS or MP shipment UI/API is touched.

CI outputs unmatched file, detected surface symbol/route and the nearest mapped requirement. This makes reuse-first a failing contract, not a reviewer preference.

## 15. WB regression contract

For `marketplace=wildberries` and current roles/data:

- route and navigation topology is unchanged apart from removal of rejected Ozon nav;
- current FBS tabs, worklist copy, selection, supply creation/add, workspace stages, pick, marking, print, boxes/trbx, supply QR, deliver/tracking and status grouping remain observable-identical;
- current `/app/ff/mp-shipments` WB create, product plan, pick, PackagingTask, boxes and ship remain observable-identical;
- WB credentials/sync card, catalog fields/mapping and stock sync do not call generic Ozon code paths;
- full existing WB backend tests and FBS/MP Playwright suites are mandatory, plus characterization tests comparing old and adapter projections for the same fixtures.

No shared switch ships until WB adapter projection equality is proven for current response fields and browser path.

## 16. Vertical slices: вместе дают полный Ozon scope без parallel UI

Each slice is one or more atomic feature cards through BA → Product Before Dev → Atomic Dev → Code Review → Product Browser Review. The slices are ordered to avoid changing all surfaces at once.

| Slice | Existing surface | Complete user outcome | Negative/recovery proof |
|---|---|---|---|
| S0R Replacement reuse prototype | All bounded routes in §13 | Owner can click complete cross-process concept with zero Ozon routes | Rejected prototype absent; WB browser regression |
| S1 Account/discovery/isolation | `/seller/settings` | Seller admin connects complete account, sees roles/expiry/capabilities; incomplete pair calls no network | identity mismatch, expired role, secret redaction, two sellers/two accounts |
| S2 Import-only catalog/mapping | `/app/ff/products` | FF admin imports and confirms account-scoped mappings | ambiguous barcode, partial pagination, no product/stock write |
| S3 Reliability spine | Inline states in same settings/documents | Jobs, checkpoints, inbox, ledger and assets recover truthfully | 429, timeout uncertain, duplicate/out-of-order push, readback-before-retry |
| S4 FBS intake/projection/reserve | `/app/ff/fbs` queue | Multi-line postings appear once with line quantities/blockers and reserve | shortage, unmapped line, unknown status; WB projection equality |
| S5 FBS pick/exemplars | Current FBS workspace composition/pick/packing | Operator scans by line/unit and fixes rejected required data | wrong location/product, duplicate scan, reject/correct, cancel-after-pick |
| S6 FBS packages/labels/handover | Current workspace packing/boxes | Partial package, current label and one-by-one/carriage complete safely | incorrect dimensions, label pending/superseded, uncertain ship/arbitration |
| S7 FBO route/supply async | Current MP shipment header/products | Planner creates supported Ozon supply from existing document | unsupported route, timeslot conflict, operation timeout/readback |
| S8 FBO pick/pack/cargo/TGM/labels | Existing pick/packaging/boxes | Operator prepares physical boxes and binds required external cargo/TGM | rules drift, partial cargo failure, failed/superseded label |
| S9 FBO handover/acceptance/reconciliation | Same MP document/footer | Planner sees distinct shipped/accepted/act states and resolves discrepancy | beta act absent, manual fallback, no false acceptance |
| S10 Returns | Existing reception/sorting/seller documents | Matched/unmatched FBS/FBO returns enter quarantine and are inspected | duplicate/unmatched/damaged, no inventory before restock post |
| S11 Integration/hardening | Same five zones | Full Ozon FBS/FBO/catalog/settings/returns/reconciliation with account isolation | WB full regression, load/backfill, kill switches, final visible-browser integration |

S1–S11 sum to connection, catalog, FBS, FBO, packages/labels/documents, cargo/TGM, statuses, returns, reconciliation and account isolation. Completion of an early slice is not «модуль Ozon готов». If an external capability is absent, the slice completes only with discovered absence, manual/read-only fallback and truthful UI; it must not claim unavailable automation.

## 17. Conscious non-goals

- No standalone Ozon route, dashboard, nav section, FBS/FBO/returns/catalog/connection screen, tab, document or workspace.
- No redesign of existing WB FBS or MP shipment flow.
- No migration/rename of WB tables in the first program.
- No Ozon product create/update/import mutation and no stock publication.
- No universal marketplace status enum pretending WB and Ozon lifecycles are identical.
- No automatic split/package/cancel/retry without current `available_actions` and readback.
- No auto-restock or automatic quality decision for returns.
- No guessed label size, cargo/TGM rule, timeslot, limit or idempotency guarantee.
- No Yandex/other marketplace work in these slices.
- No production implementation or acceptance based on this architecture alone.

## 18. Риски и меры

| Риск | Мера |
|---|---|
| Multi-line posting flattened into false orders | Additive line/unit/package aggregate; one posting → one work item view |
| Operator flow duplicated | REUSE_MAP + CI surface detection + zero new route rule |
| Ozon semantics erased by generic DTO | Provider-specific conditional payloads and raw external state under shared workflow |
| WB regression from facade | Existing WB models untouched, characterization equality, full backend/e2e/browser regression |
| Account data leak | account on every external key; tenant→seller→account authorization order |
| Duplicate mutation after timeout | immutable intent fingerprint, uncertain state, mandatory readback |
| Push/pagination loss | resource/version/filter checkpoint, transactional commit, polling authority |
| Wrong/stale label | taxonomy, version/checksum/supersession, ready/current-only print |
| WMS box confused with package/cargo/TGM | explicit link tables and separate names in one current packaging zone |
| False delivered/accepted | local physical and external lifecycle stored separately |
| Return increases stock too early | quarantine + inspection + existing posted movement only |
| Large existing screens become fragile | bounded zones, atomic slices, no adjacent redesign, per-surface browser gate |
| External API drift/beta removal | version-frozen fixtures, capability off, raw enum tolerance, per-action kill switch |

## 19. Вопросы владельцу

**Вопросов владельцу: 0.** Поручение требует безопасных fallback без остановки. Неизвестные auth mode, account capabilities, label formats, cargo/TGM rules и return disposition policy закрыты в §§2, 5 и 6 через `pending_credentials`, discovery, version-frozen fixtures, readback, binary pass-through, quarantine и `needs_shift_lead`.

## 20. Передача следующему этапу

Следующее допустимое действие ведущего — отдельный replacement prototype call строго по §13 и `REUSE_MAP.json`. Prototype developer first removes rejected standalone route/nav code, then changes only bounded zones of existing routes under fixture mode. После visible-browser approval BA режет S1–S11 на atomic cards. Production development до нового `PRODUCT_APPROVED_FOR_DEV` запрещён.

Architecture acceptance requires: valid `REUSE_MAP.json`; zero new UI surfaces; machine gate design; complete slices; separate Git commit/SHA. Push/deploy/browser acceptance are separate states and are not implied by this document.
