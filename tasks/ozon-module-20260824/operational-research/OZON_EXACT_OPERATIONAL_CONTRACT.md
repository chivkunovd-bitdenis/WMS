# Точный операционный контракт Ozon: исправление по live evidence

**Call:** `35-ozon-operational-research-live-evidence-correction-path-authorized`  
**Срез текущего WMS:** Git `41dd1549d1f6ccf26378469234ce0ecdf61b282a`  
**Live evidence:** 2026-08-24T21:08:14Z–2026-08-24T21:12:37Z UTC  
**Граница:** только исследование. Production-код, UI, тесты, принятые owner-артефакты, raw evidence и run-ledgers не менялись; provider calls и commit не выполнялись.

## Исследовательские вопросы

1. Какие operation id, HTTP method и path из 90 строк контракта действительно присутствуют в живой официальной документации Ozon Seller API?
2. Какие поля видны в live DOM, а какие точные вложенные типы, requiredness и значения по-прежнему опираются только на сохранённый schema snapshot?
3. Какие обязательные и условные действия FBS подтверждают актуальные официальные инструкции по сборке и передаче?
4. Когда FBS shipment/carriage обязателен, а когда отправления можно передавать по одному без его формирования, подтверждения и общего штрихкода?
5. Является ли FBO TGM универсальным этапом или активируемым паллетным сценарием для конкретной поставки/возможности?
6. Что методы returns list/giveout действительно доказывают и чего они не доказывают о физической проверке и остатках?
7. Какие возможности конкретного аккаунта, метода доставки и поставки нельзя проверить без Client-Id, несмотря на найденный API key marker?
8. Что уже существует в текущем WMS и потому не создаёт основания менять экран, вкладку, модальное окно, дизайн или складскую топологию?

## Изученные первичные источники

Полный журнал источников и контрольные суммы находится в [`OZON_OFFICIAL_SOURCE_LEDGER.md`](./OZON_OFFICIAL_SOURCE_LEDGER.md).

- [Живая документация Ozon Seller API 2.1](https://docs.ozon.ru/api/seller/?__rr=1&abt_att=1). Lead зафиксировал 90/90 operation rows, 90/90 method matches и 90/90 path matches в [`33-lead-live-official-validation.json`](../../../docs/runs/ozon-module-20260824/33-lead-live-official-validation.json).
- [Та же официальная документация, 41 core operation section](https://docs.ozon.ru/api/seller/?__rr=1&abt_att=1). 41/41 секций найдены и сохранены до example payloads в [`33-lead-live-core-sections.json`](../../../docs/runs/ozon-module-20260824/33-lead-live-core-sections.json).
- [Сборка отправлений на FBS](https://seller-edu.ozon.ru/libra/fbs/ozon-logistika/sborka-otpravlenii-na-fbs): live страница от 13 июля 2026.
- [Отгрузка отправлений на FBS](https://seller-edu.ozon.ru/libra/fbs/ozon-logistika/otgruzka-otpravlenii-na-fbs): live инструкция о документах, пункте приёма, курьере и проверке следующего статуса.
- [Работа с транспортными грузоместами в поставках FBO](https://dev.ozon.ru/start/525-Rabota-s-transportnymi-gruzomestami-TGM-v-postavkakh-FBO/): live guide от 4 июня 2026.
- [Официальный канал Ozon Seller API](https://t.me/s/OzonSellerAPI?before=684) и [Ozon Marketplace](https://t.me/s/ozonmarketplace?before=2781): версии методов, beta FBO acts и поштучная FBS-передача.
- [Сохранённый OpenAPI transport](https://github.com/MissiaL/ozon-api/blob/main/references/ozon-seller-openapi.json) использован только для вложенных schema details, которых нет в live evidence. Это не первичный источник; такие детали остаются `CONFLICT`.

## Политика доказательности

`CONFIRMED_OFFICIAL` применяется к точному claim scope, который виден в живом Ozon-owned источнике. `CONFIRMED_ACCOUNT` не применяется: аутентифицированных account calls не было. `CONFLICT` сохраняется для вложенных типов, requiredness, enum, описаний и полей, которые live evidence не подтверждает точно. `UNKNOWN_EXHAUSTED` применяется только к конкретным account/supply/delivery-method фактам, которые нельзя получить из-за отсутствующего Client-Id.

Это не массовое повышение 90 полных строк. Во всех 90 строках машинного контракта теперь отдельно записано: identity/method/path подтверждены официально; field-name reconciliation подтверждает только присутствие 1 551 имён; 83 невидимых имени в 15 строках перечислены явно; точная вложенная schema semantics остаётся `CONFLICT`.

## Подтверждённые факты

### Seller API

- В live Ozon Seller API найдены все 90 ожидаемых operation ids; для каждой строки совпали HTTP method и path.
- В DOM сверено 1 634 ожидаемых имени полей: 1 551 видны, 83 не видны. 75 операций не имеют невидимых имён. Эта метрика не доказывает тип, requiredness или смысл вложенного поля.
- Все 41 запрошенные core-секции непустые. 39 совпадают с method/path строк контракта; ещё две live official секции — `POST /v1/cluster/list` и `POST /v1/returns/company/fbs/info` — записаны как дополнительные наблюдения, а не молча подменяют строки `/v2/cluster/list` и unified returns.
- Live core section `POST /v4/posting/fbs/ship` прямо говорит, что HTTP 200 не гарантирует успешную сборку; требуется `/v3/posting/fbs/get`, а `result.substatus = ship_failed` требует повторной сверки/сборки.

### FBS сборка и передача

- Одна упаковка Ozon — отдельное отправление со своей этикеткой; разделение заказа после перехода в «Готов к отгрузке» уже недоступно.
- Формировать shipment/carriage нужно только для поштучной передачи курьеру и доверительной приёмки. Во всех остальных случаях инструкция разрешает перейти к печати этикетки.
- Для передачи в пункте приёма официальная инструкция допускает поштучный сценарий: используется штрихкод/этикетка отправления без обязательного формирования и подтверждения общего shipment/carriage и без его общего штрихкода. Это возможность, зависящая от метода и точки, а не универсальный default для любого аккаунта.
- Старый carriage остаётся применимым для поштучного курьера, доверительной приёмки и при необходимости транспортных документов. Поэтому правило имеет статус `CAPABILITY_CONDITIONAL`, а не «carriage всегда обязателен» и не «carriage всегда не нужен».
- Этикетка Ozon принадлежит отправлению и печатается после сборки. Это точечная provider-специфика в уже существующей зоне печати/передачи; она не доказывает необходимость нового экрана, этапа или дизайна.

### FBO GM/TGM

- Live guide описывает TGM как активируемый сценарий распределения GM по паллетам для больших объёмов: сначала `/v1/cargoes/transport/activate`, затем create/status, bind/status и отдельные pallet labels.
- TGM не универсален для каждой FBO поставки. Его scope определяется конкретной supply/capability и активированным сценарием.
- Обычные GM также нельзя объявить универсально одинаковыми для всех поставок: обязательность, допустимое распределение и состав должны читаться для конкретной supply через `/v1/cargoes/rules/get`, `/v1/cargoes/supplies/get` и cargo readback.
- Локальный WMS box, Ozon GM и Ozon TGM остаются разными идентичностями. Evidence не даёт права переименовать или слить их.

### Возвраты

- `/v1/returns/list` — read contract о marketplace return; giveout methods дают capability/readback, barcode и PDF/PNG для выдачи.
- Эти контракты не описывают новую инспекционную UI, локальную физическую приёмку или автоматическое изменение sellable stock. Следовательно, они не являются доказательством нового экрана и не являются доказательством внешнего restock.
- Более сильное утверждение «Ozon никогда автоматически не возвращает товар в продажу» этими read/giveout contracts не доказано и не принимается.

### Credentials и provider calls

- В обозначенном shared Git marker найдено только имя `OZON_TEST_API_KEY`; переменная непустая. Значение не выводилось и не сохранялось.
- `Client-Id` в marker отсутствует. Полную пару обязательных headers сформировать нельзя, поэтому выполнено ровно 0 authenticated provider calls.
- Отсутствие account readback ограничивает только account/supply/delivery-method capability; оно не отменяет live public documentation evidence.

## Текущий WMS baseline

Это чтение checkout на SHA `41dd1549d1f6ccf26378469234ce0ecdf61b282a`, не browser acceptance и не production proof.

- `frontend/src/App.tsx` уже маршрутизирует `/ff/fbs`, `/ff/fbs/stock-sync`, `/ff/mp-shipments` и `/ff/inbound`.
- `FfFbsSupplyWorkspace.tsx` уже содержит стадии `Состав` → `Подбор` → `Упаковка и маркировка` → `Короба`; `FfSuppliesShipmentsPage.tsx` уже содержит `Товары` → `Подбор` → `Упаковка` и работу с коробами.
- Backend уже разделяет `FbsOrder`, `FbsSupply`, `FbsPackingBox`, marketplace unload request/line/box и `FbsWarehouseBinding`.
- Allocation использует warehouse binding, row locking (`with_for_update`) и `Product.fbs_stock_limit`; это локальная защита WMS, а не статус Ozon.
- Подбор, сортировка, упаковка, маркировка, короба, печать, передача, inbound/returns и catalog mapping уже имеют существующие зоны. Исследование не обнаружило provider-факта, который сам по себе требовал бы менять их топологию или дизайн.

## Противоречия

1. Call 33 утверждал, что live Browser/official docs недоступны. Lead evidence опровергает это: 90/90, 41/41 и 3/3 live official pages сохранены.
2. Method/path identity всех 90 строк подтверждена, но это не подтверждает каждое вложенное поле. Поэтому identity получает `CONFIRMED_OFFICIAL`, а неподдержанная вложенная точность остаётся `CONFLICT`.
3. Поштучная FBS-передача возможна без carriage, но courier piecewise и entrusted acceptance требуют его. Разрешение: `CAPABILITY_CONDITIONAL` по delivery method/point.
4. TGM подтверждён live guide, но как активируемая паллетная возможность для больших объёмов; universal FBO stage из этого не следует.
5. Returns read/giveout подтверждены, но inspection UI и external restock из них не следуют.
6. Общая инструкция о «конкретной передаче архитектору» конфликтует с более точной acceptance Call 35. Для этого call действует запрет на architect handoff, ARCH/UI contract и mockup.

## Неизвестные

После live corrections неизвестными остаются только concrete capability facts, перечисленные в [`OZON_RESEARCH_UNKNOWN_LEDGER.md`](./OZON_RESEARCH_UNKNOWN_LEDGER.md): доступность allowlisted reads конкретному аккаунту; FBS delivery method/point handover capability; GM/TGM rules конкретной FBO supply; обязательность beta act для конкретной supply. Причина одна: API key marker найден, но Client-Id отсутствует, поэтому account call невозможен. Concrete return eligibility при необходимости входит в общий account-capability scope и не превращается в отдельное широкое правило.

## Риски

- Принять 90/90 method/path как доказательство всех 24 658 строк nested schema и потерять 83 явно невидимых field names.
- Сделать carriage либо универсально обязательным, либо универсально запрещённым и сломать courier/entrusted/point-specific процесс.
- Превратить TGM guide для pallet/large-volume в обязательный FBO этап для любой supply.
- Приравнять WMS box к GM/TGM и перепутать provider label ownership.
- Превратить returns read/giveout в новую inspection UI или автоматический restock без evidence.
- Считать найденный API key достаточным для вызова и пытаться угадать Client-Id; это запрещено и технически не формирует валидную auth pair.
- Назвать исследование implementation permission или screen acceptance; ни того, ни другого этот call не выдаёт.

## Конкретная передача после исследования

Architect handoff отсутствует и не создаётся. После явного принятия этого исследования root допустимая последовательность такова: reuse-first correction текущей screen-readiness на существующих экранах, затем отдельные atomic developer slices. Этот текст не является разрешением на разработку, новый ARCH/UI contract, mockup, экран, вкладку, modal, workspace, redesign или изменение production-кода.
