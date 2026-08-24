# Ozon в WMS: исследовательское досье для архитектуры

**Call ID:** `01-ozon-domain-research`

**Дата исследования и доступа к внешним источникам:** 24 августа 2026 года

**Исследованный checkout:** `codex/ozon-module-sol-20260824`, исходный SHA `d0cfab0abc3054183081925a860c27b15f2f4ebc`

**Граница работы:** исследование без production-кода, без проектирования итогового интерфейса и без изменения данных Ozon.

## Как читать выводы

- **Подтверждено Ozon** — факт из актуальной официальной документации, официального канала изменений Seller API или официального канала продавцов Ozon.
- **Наблюдение по коду** — факт из указанного checkout WMS.
- **Вывод** — интерпретация подтверждённых фактов и кода; это ещё не архитектурное решение.
- **Неизвестно** — данных недостаточно, либо факт зависит от конкретного кабинета, способа доставки, категории товара или ещё не зафиксированной версии схемы API.

Главный результат исследования: «добавить ещё один API-клиент» недостаточно. У Ozon отправление FBS содержит строки товаров и может делиться на несколько отправлений/упаковок, а сдача может идти поштучно без обязательной общей отгрузки. Текущая WMS-модель, напротив, кодирует один товар на WB-заказ и строит процесс вокруг WB-поставки и грузомест. Это подтверждённый разрыв доменной модели, который нужно разрешить до прототипа.

## Вопросы исследования

1. Как безопасно и однозначно связать WMS tenant, продавца, кабинет Ozon и набор прав, не смешивая их с Wildberries?
2. Какие актуальные read-only методы нужны для импорта кабинета, товаров, складов, FBO-поставок, FBO/FBS-отправлений и возвратов?
3. Как выглядит полный FBS-цикл: получение, сопоставление, резерв, маркировка, упаковка, этикетка, сдача, акты, статусы, отмены и возвраты?
4. Как выглядит полный FBO-цикл: заявка, таймслот, состав, грузоместа/транспортные грузоместа, этикетки, сдача, приёмка, акты и возвраты?
5. Какие штрихкоды, QR-коды, маркировочные данные и печатные документы являются разными сущностями, а не вариантами одного WB-стикера?
6. Какие механизмы синхронизации, пагинации, лимитов, повторов и восстановления подтверждены Ozon?
7. Что в текущей WMS можно считать общим ядром, а что жёстко кодирует WB?
8. Какие решения и доказательства нужны архитектору до прототипа, чтобы не затронуть работающие WB-потоки и не включить публикацию остатков Ozon?

## Изученные источники

### Официальные источники Ozon

Все внешние источники ниже открывались или проверялись 24 августа 2026 года.

1. [Ozon Seller API — официальная документация](https://docs.ozon.ru/api/seller/) и [официальная лента изменений](https://docs.ozon.ru/api/seller/#tag/News). Интерактивная страница документации в исследовательской среде уходила в redirect loop, поэтому актуальность версий дополнительно сверялась по официальной ленте уведомлений Ozon. Это ограничение явно учтено в разделе неизвестных.
2. [Официальный канал Ozon Seller API](https://t.me/s/ozonsellerapi), в частности публикации 9 июля — 11 августа 2026 года: переход на `/v3/posting/fbo/list`, `/v4/posting/fbs/list`, `/v4/posting/fbs/unfulfilled/list`; новые поля FBS; push-типы FBO; бета-методы актов FBO; обновления Seller API.
3. [Официальная публикация о транспортных грузоместах FBO](https://dev.ozon.ru/start/525-Rabota-s-transportnymi-gruzomestami-TGM-v-postavkakh-FBO/) и [гайд по интеграции FBO со сканером](https://dev.ozon.ru/start/526-Gaid-integratsiia-metodov-Seller-API-FBO-so-skanerom/), опубликованные Ozon в июне 2026 года. Гайд заявляет полный цикл от выбора поставки до распределения товаров и печати этикеток.
4. [Официальная публикация о бета-методах актов FBO](https://dev.ozon.ru/news/781-Novye-beta-metody-dlia-raboty-s-aktami-FBO-v-Seller-API/) от 11 августа 2026 года.
5. [Официальная публикация о валидации атрибута 23536 «Нужен код маркировки»](https://dev.ozon.ru/news/777-Izmenenie-validatsii-atributa-23536-Nuzhen-kod-markirovki-v-Seller-API/) и официальная лента Seller API о ставшем обязательным для многих категорий атрибуте 22232 «Код ТН ВЭД ЕАЭС» (июнь–июль 2026 года).
6. [Официальный канал продавцов Ozon: поштучная сдача FBS по штрихкоду отправления](https://t.me/s/ozonmarketplace?before=2781). На дату исследования Ozon сообщает, что способ доступен всем продавцам; прежний процесс с формированием отгрузки остаётся опционально, например для транспортной накладной.
7. [Официальная лента Seller API: асинхронная этикетка и ошибки упаковки](https://t.me/s/ozonsellerapi?before=648), запись от 10 марта 2026 года о `/v2/posting/fbs/package-label/create` и `INCORRECT_OVH_FOR_POSTING` для `/v4/posting/fbs/ship`.
8. [Официальная лента Seller API: актуальные версии маркировочных экземпляров](https://t.me/s/OzonSellerAPI?before=605), записи 13–16 января 2026 года; и [изменения полей маркировки/IMEI](https://t.me/s/OzonSellerAPI?before=552) от сентября 2025 года.
9. [Официальная лента Seller API: текущие склады и перевозки](https://t.me/s/OzonSellerAPI?before=639): `/v2/warehouse/list`, `/v2/carriage/delivery/list`, `/v1/carriage/act-discrepancy/pdf`, правила API-ключей и `/v1/roles`.
10. [Официальная лента Seller API: единый список возвратов и пропуска](https://t.me/s/OzonSellerAPI?before=428) и [методы возвратов FBS/пропусков](https://t.me/s/OzonSellerAPI?before=393). Старые `/v3/returns/company/fbo` и `/v3/returns/company/fbs` были заменены `/v1/returns/list`.
11. [Официальная лента Seller API: текущий FBS split/partial package](https://t.me/s/OzonSellerAPI?before=375) и [переход к `/v4/posting/fbs/ship`](https://t.me/s/OzonSellerAPI?after=350).
12. [Официальная лента Seller API: private apps, OAuth и листы подбора](https://t.me/s/OzonSellerAPI?before=579). Ozon описывает частные приложения с OAuth-клиентом и методы листов подбора FBS.
13. [Ozon App Store для интеграторов](https://dev.ozon.ru/appstore/). Официальная публикация Ozon от августа 2026 года указывает OAuth 2.0 как механизм авторизации внешних пользователей для SaaS-интеграций.

### Источники в текущем WMS

- [Запрос владельца](REQUEST.txt) — точная формулировка: «Сделать модуль Ozon».
- [MVP-решения](../../MVP_DECISIONS_RU.md) — tenant/seller-модель, текущая WB-интеграция, складские термины и границы MVP.
- [Правила feature gate](../../WMS_FEATURE_GATE_PROTOCOL_RU.md) — исследование предшествует Product/Dev; это досье не является разрешением на разработку.
- Backend: `backend/app/models`, `backend/app/api`, `backend/app/services`, `backend/app/tasks` и `backend/app/main.py` на указанном SHA.
- Frontend: `frontend/src/App.tsx`, `frontend/src/layouts/AuthedAppLayout.tsx`, `frontend/src/screens/v2`, `frontend/src/components` и `frontend/src/lib/fbsApi.ts` на указанном SHA.
- Проверки: `backend/tests/test_wildberries_*`, `backend/tests/test_fbs_*`, `frontend/tests-e2e/ff-fbs-*.spec.ts`, `frontend/tests-e2e/wildberries-admin-ui.spec.ts` и связанные marking/packing/printing сценарии.

## Подтверждённые факты Ozon

### Подключение кабинета и multi-seller

1. **Подтверждено Ozon.** Прямая авторизация Seller API через API-ключ использует пару идентификаторов кабинета: `Client-Id` и `Api-Key`. Наличие только API-ключа не позволяет однозначно и безопасно выполнить запрос от имени кабинета.
2. **Подтверждено Ozon.** `/v1/seller/info` — read-only метод сведений о кабинете; `/v1/roles` возвращает права ключа и, после обновлений 2026 года, срок действия (`expires_at`). С 13 февраля 2026 года официальный канал Ozon сообщает шестимесячный срок действия вновь создаваемого API-ключа.
3. **Подтверждено Ozon.** Для интеграционных сервисов Ozon поддерживает частные/магазинные приложения с OAuth. Это отдельная модель подключения, а не ещё одно поле рядом с прямым API-ключом.
4. **Вывод.** Идентичность должна учитывать как минимум marketplace, внешний кабинет, способ авторизации, набор прав и срок действия. Один глобальный Ozon-ключ или один `mp_api_key` на продавца не доказывает корректную multi-seller-модель.
5. **Неизвестно.** Какой способ подключения будет разрешён конкретному WMS-развёртыванию — прямые пары `Client-Id`/`Api-Key`, private app OAuth или оба режима. Это решение ведущего/архитектора после проверки условий Ozon App Store.

### Товары, карточки, сопоставление и остатки

1. **Подтверждено Ozon.** Актуальный read-only контур товаров включает `/v3/product/list`, `/v3/product/info/list`, `/v4/product/info/attributes`, `/v4/product/info/stocks`. В июле 2026 года `/v3/product/list` получил фильтр `skus` и возвращаемый `sku`.
2. **Подтверждено Ozon.** В API одновременно встречаются seller `offer_id`, Ozon `product_id` и Ozon `sku`. Их нельзя считать одним идентификатором. У товара могут быть штрихкоды, а у отправления, упаковки, отгрузки и грузоместа — свои отдельные коды.
3. **Подтверждено Ozon.** Дерево и атрибуты категорий читаются через семейство `/v1/description-category/*`. Для большинства затронутых категорий Ozon требует атрибут 22232 «Код ТН ВЭД ЕАЭС»; без него SKU создать нельзя. Атрибут 23536 управляет требованием кода маркировки.
4. **Подтверждено Ozon.** Текущий read-only метод остатков по складам продавца — `/v2/product/info/stocks-by-warehouse/fbs`; `/v1/product/info/stocks-by-warehouse/fbo` добавлен в 2026 году для FBO. `/v1/analytics/stocks` с 17 августа 2026 года возвращает данные в реальном времени.
5. **Подтверждено Ozon.** `/v2/products/stocks` изменяет остатки. В рамках этого исследования и исходного поручения он запрещён и не вызывался.
6. **Подтверждено Ozon.** `/v3/product/import` и другие методы изменения товара публикуют/изменяют карточку. Они не относятся к безопасному импорту и не вызывались.
7. **Вывод.** Сопоставление WMS SKU с Ozon следует исследовать как связь many-to-many по marketplace account + внешним идентификаторам, а не добавлением одного `ozon_id` в `products` по аналогии с `wb_nm_id`.

### Склады и способы доставки

1. **Подтверждено Ozon.** Для складов продавца актуальна `/v2/warehouse/list`; старая `/v1/warehouse/list` отключена в апреле 2026 года. Ответ `/v2/warehouse/list` содержит пагинацию (`has_next`).
2. **Подтверждено Ozon.** `/v2/delivery-method/list` и `/v2/carriage/delivery/list` отражают способы доставки и отгрузки; старые версии `v1` отключены. `/v1/warehouse/ozon/list` добавлен как бета-метод списка складов Ozon, а `/v1/warehouse/fbo/seller/list` — для FBO-складов продавца.
3. **Подтверждено Ozon.** Ограничения доставки FBS могут зависеть от товара и склада; Ozon добавил `/v1/warehouse/warehouses-with-invalid-products` и `/v1/warehouse/invalid-products/get`.
4. **Вывод.** Физический склад WMS, склад продавца Ozon, склад/точка Ozon, delivery method и carriage — пять разных сущностей. Текущее WB-сопоставление «виртуальный склад → физический склад» не покрывает всю эту топологию.

## FBS: подтверждённый цикл end to end

### 1. Получение и отслеживание отправлений

- **Подтверждено Ozon.** Для новых/неисполненных отправлений следует использовать `/v4/posting/fbs/unfulfilled/list`, для общего списка — `/v4/posting/fbs/list`; версии `v3` заявлены к отключению 31 августа 2026 года. Деталь отправления остаётся в `/v3/posting/fbs/get`.
- **Подтверждено Ozon.** В ответах есть `posting_number`, массив `products`, требования к экземплярам/маркировке, `status`, `substatus`, `available_actions`, аналитические даты и сведения о способе доставки. В июле 2026 года добавлены `integration_type_flow` и `sorting_center`.
- **Подтверждено Ozon.** Push настраивается семейством `/v1/notification/set|update|check|delete|enable|list|push-type/list`. Существуют события нового отправления, отмены, смены статуса и дат; в августе 2026 года добавлены также FBO-типы.
- **Подтверждено Ozon.** Документация предупреждает, что push может запаздывать; polling списка неисполненных отправлений остаётся механизмом восстановления.
- **Вывод.** Нужны оба канала — push как ускорение и polling как источник eventual consistency (сходимости состояния), с дедупликацией по marketplace account + `posting_number` + версии/времени события.

### 2. Multi-item, split и внутренний резерв

- **Подтверждено Ozon.** Одно FBS-отправление содержит `products[]`; количество каждой позиции не обязано быть равно единице.
- **Подтверждено Ozon.** `/v1/posting/fbs/split` делит заказ на отправления до сборки. `/v4/posting/fbs/ship/package` выполняет частичную сборку и создаёт отдельное отправление/пакет; для созданного отправления документирован статус `awaiting_deliver`.
- **Вывод.** «Заказ», «отправление», «строка товара», «экземпляр товара» и «упаковка» должны оставаться разными уровнями. Резерв и подбор должны происходить по строкам/количеству, а не один раз на `posting_number`.
- **Неизвестно.** Какие варианты split разрешены тестовому кабинету и категориям владельца. Это можно подтвердить только чтением `available_actions` и требований конкретных отправлений; мутирующий split в исследовании запрещён.

### 3. Маркировка, обязательные данные и проверка

- **Подтверждено Ozon.** В актуальной группе методов используются `/v6/fbs/posting/product/exemplar/create-or-get`, `/v6/fbs/posting/product/exemplar/set`, `/v5/fbs/posting/product/exemplar/validate`, `/v5/fbs/posting/product/exemplar/status` и `/v1/fbs/posting/product/exemplar/update`. Более старые `v4/v5` create/set/status/validate были удалены из документации 13 января 2026 года.
- **Подтверждено Ozon.** Требования могут включать коды маркировки, IMEI, GTIN и вес экземпляра. В ответах отправления есть списки товаров, которым эти данные нужны; проверка имеет отдельные статусы и ошибки.
- **Подтверждено Ozon.** Для части заказов юридических лиц требуется страна происхождения; официальный API содержит методы списка/установки страны товара в отправлении. Установка — мутирующее действие и не выполнялась.
- **Вывод.** Локальный «КИЗ принят WMS» не равен «Ozon подтвердил экземпляр». Нужны отдельные локальный скан, отправка, внешний validation status и возможность корректировки до необратимой упаковки.
- **Неизвестно.** Точный набор требований определяется карточкой, категорией, схемой, страной и конкретным posting; его нельзя безопасно захардкодить из WB `required_meta_json`.

### 4. Упаковка, этикетки, штрихкоды и QR

- **Подтверждено Ozon.** Сборка выполняется `/v4/posting/fbs/ship`; частичная сборка — `/v4/posting/fbs/ship/package`. Операция зависит от текущего статуса и обязательных данных. Для некорректных габаритов/веса документирована ошибка `INCORRECT_OVH_FOR_POSTING`.
- **Подтверждено Ozon.** Текущий асинхронный путь печати использует `/v2/posting/fbs/package-label/create`, затем `/v1/posting/fbs/package-label/get`. Старый бинарный `/v2/posting/fbs/package-label` всё ещё упоминается в документации 2026 года, но архитектору нельзя считать его единственным путём без фиксации текущей схемы.
- **Подтверждено Ozon.** Этикетка печатается только для подготовленного к отгрузке отправления (`awaiting_deliver`). На поштучной сдаче ключевым идентификатором является штрихкод самого отправления.
- **Подтверждено Ozon.** `/v1/posting/fbs/restrictions` возвращает ограничения упаковки. Их нужно читать для конкретного отправления; универсальный размер короба или паллеты из исследованных источников не следует.
- **Вывод.** Нельзя смешивать product barcode, marking code, posting barcode, package label, warehouse/pass barcode и carriage/act barcode в одном поле `sticker_code`.
- **Неизвестно.** Точные размеры листа/термоэтикетки, ориентация, допустимые форматы ответа и ограничения для конкретного способа доставки не были доступны из интерактивной схемы из-за redirect loop и требуют version-frozen OpenAPI/живого read-only ответа перед прототипом печати.

### 5. Сдача, отгрузка и акты

- **Подтверждено Ozon.** На дату исследования всем продавцам доступна поштучная сдача: упаковать отправление, наклеить этикетку и передать в настроенный пункт по штрихкоду отправления. Формировать общую отгрузку и отдельный штрихкод отгрузки не обязательно.
- **Подтверждено Ozon.** Старый процесс с формированием carriage остаётся доступен, если нужна транспортная накладная. Для отдельных сортцентров, пропусков и доверительной приёмки действуют дополнительные возможности.
- **Подтверждено Ozon.** Семейство carriage включает создание/получение, назначение postings, approve/cancel, pass и актуальный `/v2/carriage/delivery/list`. Семейство актов FBS включает `/v2/posting/fbs/act/create`, `/check-status`, `/get-pdf`, `/get-postings`; `/v1/carriage/act-discrepancy/pdf` даёт акт расхождений.
- **Вывод.** Общая «поставка FBS» не может быть обязательным родителем каждого Ozon posting. Carriage/act должен быть capability-dependent (зависеть от доступного действия и способа сдачи), а не универсальным этапом.
- **Неизвестно.** Требуется ли бумажный/электронный акт конкретному кабинету, стране и способу доставки; это нельзя определить без `delivery_method`, ролей и реальных `available_actions`.

### 6. Статусы, отмены, ошибки и восстановление

- **Подтверждено Ozon.** В FBS встречаются основные состояния `awaiting_packaging`, `awaiting_deliver`, `delivering`, `delivered`, `cancelled`, а также arbitration-состояния; `substatus` и `available_actions` уточняют допустимое действие. Перечень может расширяться, поэтому основной status не является достаточной машиной состояний.
- **Подтверждено Ozon.** Ozon может отменить отправление до/после сборки; деталь содержит структуру cancellation. Продавец может отменять только когда действие разрешено; результат отмены/операции нужно сверять отдельным status/readback методом.
- **Подтверждено Ozon.** Если переданное отправление не отсканировано Ozon, предусмотрен путь арбитража. При расхождении carriage существует отдельный PDF-акт расхождений.
- **Подтверждено Ozon.** API возвращает обычные HTTP-ошибки, включая `429 Too Many Requests`; лимиты различаются по операциям и меняются. В 2026 году Ozon расширял диагностические заголовки 429 и ввёл объединённые лимиты для группы товарных операций.
- **Вывод.** Повтор мутирующего вызова нельзя делать «вслепую». Сначала должен выполняться readback текущего posting/task/operation, затем — решение о повторе. Подтверждённого универсального idempotency key для всех методов Ozon не найдено.
- **Неизвестно.** Точные числовые квоты каждого нужного метода. Их нужно снять из актуальной схемы и 429 headers, не переносить значения от отключённых версий.

### 7. Возвраты FBS

- **Подтверждено Ozon.** Единый `/v1/returns/list` заменил старые списки FBO/FBS и возвращает возвраты обеих схем. Пагинация строится на `last_id`/`has_next`, а не на одном универсальном cursor.
- **Подтверждено Ozon.** `/v1/returns/company/fbs/info` возвращает информацию и количество FBS-возвратов по точкам; существуют return giveout barcode/PDF методы и пропуска `/v1/return/pass/create|update|delete`, общий `/v1/pass/list`.
- **Подтверждено Ozon.** Настройки return point являются частью FBS-склада; в марте 2026 года обновлялись `/v1/warehouse/fbs/create/return-point/list`, `/update/return-point/list`, `/v1/warehouse/fbs/return-mile/info`.
- **Вывод.** Возврат — отдельный inbound-процесс, связанный с исходным posting и конкретным экземпляром/штрихкодом, а не просто финальный статус исходного заказа.
- **Неизвестно.** Операционный процесс осмотра, переупаковки и возврата в доступный остаток владельцем не описан в текущем WMS и требует отдельной feature card после архитектуры.

## FBO: подтверждённый цикл end to end

### 1. Подготовка товаров и направления поставки

- **Подтверждено Ozon.** Товары и их атрибуты читаются тем же каталоговым контуром; публикация через `/v3/product/import` не требуется для import-only сценария и в исследовании запрещена.
- **Подтверждено Ozon.** Для планирования используются `/v2/cluster/list`, `/v1/warehouse/fbo/seller/list`, справочник складов Ozon и информация о placement zone. В 2026 году `/v2/cluster/list` выведен из beta.
- **Подтверждено Ozon.** Существуют три актуальных варианта черновика: `/v1/draft/crossdock/create`, `/v1/draft/direct/create`, `/v1/draft/multi-cluster/create`.
- **Вывод.** Тип поставки и маршрут нельзя выводить из одного `delivery_type` WB; crossdock, direct и multi-cluster имеют разные требования и этапы.

### 2. Асинхронное создание заявки и таймслот

- **Подтверждено Ozon.** Результат черновика/таймслота читается через `/v2/draft/create/info` и `/v2/draft/timeslot/info`; заявка создаётся `/v2/draft/supply/create`, её выполнение проверяется `/v2/draft/supply/create/status`.
- **Подтверждено Ozon.** Старое семейство `/v1/draft/create*` отключено 16 марта 2026 года; его лимиты и поля нельзя переносить на текущую версию.
- **Подтверждено Ozon.** Информация о созданных заявках читается `/v3/supply-order/list` и `/v3/supply-order/get`; состав/таймслот меняются отдельными операциями со своими status endpoints.
- **Вывод.** Создание FBO supply — не синхронный INSERT. Нужна локальная операция с внешним `operation_id`, промежуточным состоянием и readback перед повтором.

### 3. Состав, грузоместа, транспортные грузоместа и печать

- **Подтверждено Ozon.** `/v1/cargoes/rules/get` даёт правила грузомест для заявок, `/v1/cargoes/get` — текущий состав, `/v1/cargoes/create` — установка грузомест, `/v2/cargoes/create/info` — результат; delete также асинхронен. В 2026 году Ozon исправил поведение `delete_current_version`: его значение влияет на перезапись существующих грузомест.
- **Подтверждено Ozon.** Официальные руководства 2026 года отдельно различают грузовые места (ГМ) и транспортные грузовые места (ТГМ), описывают распределение товара, сканирование штрихкодов и печать этикеток.
- **Подтверждено Ozon.** Семейство cargo label создаёт задачу этикеток, позволяет проверить её и получить файл. Исторически документированы `/v1/cargoes-label/create`, `/v1/cargoes-label/get`, `/v1/cargoes-label/file/{file_guid}`; текущие точные схемы нужно зафиксировать из версии документации перед прототипом.
- **Вывод.** WMS-короб, FBO cargo и transport cargo — не взаимозаменяемые понятия. Паллетирование/контейнеризация должны идти из `cargoes/rules/get` и выбранного маршрута, а не из WB `trbx`.
- **Неизвестно.** Конкретные допустимые типы паллет/ТГМ, лимиты количества и форматы этикеток для реального кабинета; без созданной заявки read-only API не даст весь контекст, а создавать её в исследовании запрещено.

### 4. Сдача, lifecycle и приёмка

- **Подтверждено Ozon.** `/v3/supply-order/get` возвращает lifecycle заявки и её supplies; отдельные методы обновления таймслота/состава имеют status endpoints и массивы ошибок. Supply можно отменить только через разрешённое действие и затем сверить состояние.
- **Подтверждено Ozon.** FBO postings читаются через актуальный `/v3/posting/fbo/list` и `/v2/posting/fbo/get`; `/v2/posting/fbo/list` отключается 31 августа 2026 года. С августа 2026 года доступны push-типы новых/отменённых/изменившихся FBO postings и изменения FBO stocks.
- **Подтверждено Ozon.** С 11 августа 2026 года бета-методы `/v1/supply-order/act/summary/get`, `/product/get`, `/accept`, `/accept/status` позволяют сверять и согласовывать акт приёмки после поставки.
- **Вывод.** «Отгружено WMS», «доставлено на Ozon», «принято», «акт согласован» и «остаток появился» — разные наблюдаемые состояния.

### 5. Ошибки, расхождения и возвраты FBO

- **Подтверждено Ozon.** Ошибки могут находиться не только в HTTP response, но и в асинхронном status результате операции. Readback заявки, грузомест и акта обязателен до повторов.
- **Подтверждено Ozon.** `/v1/returns/list` покрывает FBO и FBS; FBO-акт приёмки предоставляет построчную сверку продукта.
- **Вывод.** Для восстановления нужны два независимых контура: технический task/operation и бизнесовое состояние supply/order/act. Успешный HTTP 200 не доказывает успешную поставку.

## Пагинация, лимиты и идемпотентность

**Подтверждено Ozon:**

- разные семейства используют разные checkpoint-формы: `cursor`, `offset/limit`, `has_next`, `last_id`, временные фильтры и `operation_id`;
- `/v2/warehouse/list` использует `has_next`, `/v1/returns/list` — `last_id/has_next`; product и posting families имеют собственные формы;
- 429 является штатным ограничением, а лимиты и заголовки меняются по версиям/операциям;
- ряд мутаций асинхронен и возвращает task/operation, который надо опрашивать.

**Вывод:** один общий «page=1» или безусловный retry middleware потеряет или продублирует данные. Checkpoint должен храниться на уровне marketplace account + resource + API version + filter fingerprint. Для мутаций нужен локальный operation ledger: intent fingerprint, внешний operation/task id, last readback, финальный результат и ручной recovery state.

**Неизвестно:** универсальной гарантии идемпотентности повторного POST/PUT или единого Ozon idempotency header в изученных первичных источниках не найдено. Архитектор не должен её предполагать.

## Безопасная проверка тестового доступа

1. **Наблюдение по репозиторию.** В отдельной служебной ветке `ozon-test-key-marker-20260824`, commit `93d4cc9a511a895cec41c9d6386b93ebb87199b9`, документирован безопасный маркер: секрет хранится вне Git в общем каталоге репозитория `codex-secrets/ozon-test.env`.
2. **Санитизированный результат.** Файл существует и содержит непустую переменную типа Ozon Seller API key — `OZON_TEST_API_KEY`. Значение не печаталось, не копировалось в артефакт и не передавалось командам.
3. **Подтверждённое ограничение.** В безопасно проверенном наборе имён переменных нет `Client-Id`. Поэтому корректный Ozon Seller API запрос невозможен: API-ключ нельзя связывать с кабинетом по догадке.
4. **Фактически выполненные внешние API-вызовы:** ни одного. Не вызывались ни read-only, ни mutating endpoints. Данные Ozon, товары, отправления, поставки, остатки и настройки не менялись.
5. **Допустимый будущий read-only probe при наличии полной пары:** `/v1/seller/info`, `/v1/roles`, списки/детали products, warehouses, delivery methods, FBS/FBO postings, supply orders/cargoes и `/v1/returns/list`. Даже тогда секреты должны передаваться только в headers и не попадать в логи.
6. **Явно запрещённые классы:** product import/publish/update, `/v2/products/stocks`, FBS ship/split/cancel/act/carriage, exemplar set/update, FBO draft/supply/cargo/act accept, warehouse/push configuration и любые credential-management страницы.

## Текущий WMS baseline

Это baseline именно исследованного SHA, а не доказательство состояния production или `etalon`.

### Backend и база данных

| Область | Наблюдение по коду | Граница/разрыв для Ozon |
|---|---|---|
| Tenant и seller | `backend/app/models/seller.py:22-59`: seller принадлежит tenant. Но отношения явно названы `wildberries_credentials`, `wildberries_imported_cards`, `wildberries_imported_supplies`. | Tenant/seller пригодны как общее ядро; marketplace account/connection как самостоятельной сущности нет. |
| Credentials | `seller_wildberries_credentials.py:13-37` хранит три WB-токена и scope. `seller_marking_credentials.py:26-51` знает строку `ozon`, но хранит только один общий `mp_api_key_enc`. | Строка `ozon` относится к marking credentials и не реализует Seller API пару `Client-Id` + `Api-Key`, OAuth, roles или expiry. |
| Каталог | `product.py:35-80`: общий WMS SKU, габариты, упаковка, ЧЗ; одновременно WB-поля и unique по `wb_barcode`. | Полезны WMS product/inventory. Нет account-scoped внешних offer/product/sku/barcode mappings и истории состояния карточки. |
| Импорт карточек | `seller_wildberries_imported_card.py:16-44`: snapshot WB по `(seller_id, nm_id)` и `raw_json`. | Паттерн snapshot полезен как наблюдение, но ключ и схема WB-only; нет Ozon import. |
| Физический склад | `warehouse.py:20-58`: tenant warehouse, code, barcode, locations. | Пригоден как физический склад WMS. Не моделирует marketplace warehouse, Ozon warehouse, delivery method или return point. |
| Warehouse binding | `fbs_warehouse_binding.py:28-70`: один WB virtual warehouse привязан к WMS warehouse; stock sync включён по умолчанию. | WB-only id и семантика пула. Для Ozon нужны разные внешние узлы; default stock write противоречит запрету владельца. |
| FBS order | `fbs_order.py:151-270`: unique `(seller_id, wb_order_id)`, один `product_id`, WB ids, один набор reserve/pick/pack/sticker/meta статусов. | Не покрывает `posting -> product lines -> quantities -> exemplars -> packages`; нельзя переименовать поля и считать модель универсальной. |
| FBS statuses | `fbs_order.py:39-147`: локальные WB-ориентированные mapping/reserve/order/marking/sticker states. | Полезен принцип раздельных локальных подстатусов, но внешний status/substatus/available_actions Ozon требует отдельного сырого и нормализованного слоя. |
| FBS supply | `fbs_supply.py:20-75`: `wb_supply_id`, source `wms|wb`, delivery `warehouse_sc|pvz`, общий статус draft→done. | Ozon one-by-one handover не требует supply; FBO supply и FBS carriage имеют другую природу. |
| Boxes/trbx | `fbs_packing_box.py:23-88`, `fbs_trbx.py`: один order может принадлежать одному box, WB `trbx`. | Ozon package line quantities и FBO cargo/TGM не помещаются в constraint «один fbs_order — один box». |
| Print assets | `fbs_print_asset.py:30-117`: только `order_sticker`, `cargo_place_qr`, `supply_qr`, поле `wb_fetched_at`. | Само хранение бинарного asset/checksum/size пригодно; taxonomy и provenance WB-only, нет task/job/version/source metadata Ozon. |
| Background job | `background_job.py`, `background_job_service.py:25-30`. | Общая job-оболочка пригодна, но job types и payloads WB-specific. |

### API и сервисы

- **Наблюдение по коду.** Все routers подключены в `backend/app/main.py:104-135`; Ozon-router отсутствует.
- **Наблюдение по коду.** `backend/app/api/wildberries_integration.py` реализует status, tokens, imported cards/supplies, link-product и sync-products исключительно для WB.
- **Наблюдение по коду.** `backend/app/api/fbs_orders.py` содержит sync/worklist/list/cancel/status sync; `fbs_supplies.py` — создание/рабочее место/подбор/упаковку/печать/грузоместа/deliver/tracking; `fbs_sellers.py` — WB warehouses/offices/bindings/stock sync.
- **Наблюдение по коду.** `wildberries_client.py:25-37` и `wildberries_fbs_client.py:26-33` содержат WB paths. `wildberries_client.py:194` и `fbs_stock_publish_service.py` могут записывать абсолютные остатки в WB; этот код нельзя переиспользовать для Ozon по умолчанию.
- **Наблюдение по коду.** `wb_marketplace_orders_service.py` и многочисленные `fbs_*` services связывают WB order, WB supply, WB sticker/meta, trbx и deliver в один поток.
- **Подтверждённый baseline.** В `backend/app` нет Ozon Seller API client, Ozon models, routes, jobs, webhook receiver, poller, emulator или contract fixtures.

### Jobs

- `backend/app/tasks/background_jobs.py:30-47`: WB cards, supplies, marketplace orders и FBS stock sync.
- `backend/app/tasks/background_jobs.py:64-99`: FBS orders autopoll/full reconcile/status autopoll, stock reconcile и автоматический `fbs_stock_publish_seller`.
- **Разрыв:** есть удачный паттерн poll/reconcile, но нет marketplace account/resource checkpoint, push ingestion или Ozon task operation ledger. Существующий publisher является особым риском: Ozon stock write должен оставаться физически недоступным, а не просто скрытым кнопкой.

### Frontend и операторский поток

- `frontend/src/App.tsx:2845,2971,2987,3408`: маршруты MP shipments, FBS, FBS stock sync и отдельный Wildberries screen.
- `frontend/src/layouts/AuthedAppLayout.tsx:223-224`: навигация MP shipments; FBS flow находится в общем shell.
- `frontend/src/screens/v2/WildberriesScreen.tsx:55-260`: read-only WB cards/supplies, три WB token slots, link SKU.
- `frontend/src/screens/v2/FfFbsOrdersScreen.tsx`: WB worklist, warehouse binding, создание/добавление в WB supply.
- `frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx`: подбор по ячейке/товару, marking, упаковка, WB stickers, trbx QR и «Передать в WB».
- `frontend/src/screens/v2/FfFbsStockSyncScreen.tsx`: WB warehouses, binding и включение публикации остатков.
- `frontend/src/components/MarkingPrintDialog.tsx`: прямо кодирует WB order QR/label и печатную ленту; `FbsPrintPreviewDialog.tsx` и `FfFbsPickList.tsx` поддерживают WB supply flow.
- `frontend/src/screens/v2/SellerSettingsScreen.tsx:87-88,156,254,308`: dropdown показывает Ozon, но токены и синхронизация всё равно вызывают `/integrations/wildberries/*`. Это видимая заготовка, не работающий Ozon baseline.
- **Разрыв:** текущий интерфейс нельзя просто перекрасить и заменить «WB» на «Ozon»; различается структура отправления и необязательность общей отгрузки. Итоговый интерфейс в этом исследовании не проектировался.

### Печать

- **Наблюдение по коду.** WMS уже умеет хранить бинарные assets, checksum, размер, состояние requesting/ready/error и связывать asset с order/supply/trbx.
- **Наблюдение по коду.** Текущий конструктор смешивает WMS product label, ЧЗ и WB order QR; одна печатная «лента» является продуктовым решением под WB.
- **Разрыв:** для Ozon минимум различаются product barcode label, marking exemplar, posting/package label, posting barcode, carriage/warehouse/pass barcode, FBO cargo/TGM label и акт PDF. Требуется taxonomy, но конкретный макет не является предметом исследования.

### Тесты

- **Наблюдение по коду.** Backend покрывает WB client/token/import/order/supply/stocks/trbx/printing/marking и широкий FBS flow (`backend/tests/test_wildberries_*`, `test_fbs_*`).
- **Наблюдение по коду.** Browser/e2e покрывает `ff-fbs-orders.spec.ts`, `ff-fbs-supply.spec.ts`, `ff-fbs-full-flow.spec.ts`, `ff-fbs-stock-sync.spec.ts`, `wildberries-admin-ui.spec.ts`, marking/packaging/printing.
- **Подтверждённый baseline.** Ozon fixtures, contract snapshots, pagination/rate-limit tests, multi-item/package split tests, push/poll reconciliation, FBO cargo/act и Ozon returns tests отсутствуют.
- **Вывод.** WB tests следует сохранить как регрессионный барьер; будущие Ozon contract tests должны использовать emulator/recorded sanitized fixtures и отдельно доказывать, что stock write endpoint недостижим.

## Кандидаты на общие границы — не итоговая архитектура

Эти наблюдения передаются архитектору как материал, а не как утверждённый дизайн.

1. **Переиспользуемое ядро:** tenant, seller как бизнес-владелец, WMS product, physical warehouse/location, inventory balance/movement/reservation, packaging task, binary print storage, background job shell, role/permission framework.
2. **Marketplace-specific adapter:** auth, external account, product/posting/supply schemas, pagination, errors, capability discovery, read/write clients.
3. **Нуждается в обобщении:** внешние product mappings, warehouse/delivery bindings, order/posting/line/package/exemplar, external lifecycle snapshots, documents/labels, sync checkpoints, async operations, returns.
4. **Должно остаться WB-specific до доказанного миграционного плана:** `FbsOrder`/`FbsSupply`/`FbsTrbx`, WB token rows, WB endpoints, stock publisher, WB print tape и существующие browser flows.
5. **Будущие Yandex Market и другие площадки:** исследовать их API сейчас не нужно. Достаточно не кодировать в общем слое Ozon `posting_number`, WB `order_id`, конкретные status enums, единственный barcode или обязательную supply/carriage. Полные контракты других площадок остаются отдельным research gate.

## Противоречия

1. **Ozon multi-item против WMS one-product order.** Ozon posting содержит строки и количества; `FbsOrder` хранит один `product_id` и один набор операций.
2. **Ozon optional carriage против WMS mandatory supply workspace.** Ozon разрешает поштучную сдачу по posting barcode; WMS группирует операторскую работу вокруг `FbsSupply`.
3. **Разные упаковочные уровни.** Ozon partial package и FBO cargo/TGM не равны WB trbx и WMS box.
4. **Разные идентичности.** Ozon требует account/auth/role/expiry; WMS знает seller и WB token row, а строка `ozon` находится лишь в marking settings.
5. **Запрет Ozon stock publication против существующей автоматики.** В WMS есть периодический WB stock publisher и bindings с `stock_sync_enabled=true`. Простое параметризованное переиспользование создаст риск непреднамеренной записи в Ozon.
6. **Актуальный API против старых примеров.** В 2026 году менялись FBS/FBO lists, warehouse/carriage, exemplar, draft supply и label endpoints. Код по старому блогу технически может работать на уже отключённом контракте.
7. **«Максимум возможностей Ozon» против безопасного первого шага.** Многие ценные возможности являются mutating/beta и зависят от кабинета. Исследование подтверждает их наличие, но не подтверждает права/готовность конкретного аккаунта и не разрешает включение.
8. **Тестовый ключ против требований auth.** Найден только Api-Key marker без Client-Id; уверенный live-вывод о кабинете был бы выдумкой.
9. **Документация против доступности среды.** Официальные `docs.ozon.ru` и `dev.ozon.ru` в инструментах исследования уходили в redirect loop. Версии подтверждены официальной change feed, но точные OpenAPI schemas/label formats требуют отдельной фиксации.

## Неизвестные

1. `Client-Id`, account identity, страна кабинета, роли ключа, expiry и разрешённые scopes.
2. Доступны ли кабинету FBO direct/crossdock/multi-cluster, trusted acceptance, one-by-one FBS, carriage, pickup/courier, return giveout и beta acts.
3. Фактические seller warehouses, delivery methods, Ozon warehouses, return points и их связи.
4. Реальные status/substatus/available_actions и неизвестные enum-значения, которые вернёт текущая схема.
5. Точные квоты нужных методов, retry headers и размер допустимых батчей.
6. Точный OpenAPI schema snapshot на 24 августа 2026 года, особенно label/cargo/act binary formats.
7. Размеры и ориентация Ozon FBS/FBO этикеток, допустимые форматы печати и требования конкретного пункта сдачи.
8. Правила грузомест/ТГМ/паллет для реальных категорий и маршрута.
9. Набор обязательных TN VED, marking, IMEI, GTIN, weight/country fields на ассортименте владельца.
10. Требуется ли транспортная накладная/акт в реальном процессе владельца.
11. Семантика отмены и компенсации локального резерва для split/partial/cancelled-after-ship.
12. Операционный процесс возвратов после получения: осмотр, дефект, переупаковка, повторный доступный остаток.
13. Выбранный способ SaaS-подключения Ozon и требования регистрации приложения.
14. Совместимость будущего абстрактного слоя с Yandex Market не доказана без отдельного исследования Yandex API.

## Риски

1. **Критический — неверная гранулярность данных:** потеря строк/количеств или маркировочных экземпляров при попытке поместить Ozon posting в `FbsOrder`.
2. **Критический — непреднамеренная запись остатков:** подключение Ozon к общему `fbs_stock_publish` без deny-by-default capability.
3. **Критический — смешение кабинетов:** credential или checkpoint без account scope может читать/менять состояние другого продавца.
4. **Высокий — двойная сборка/отмена:** слепой retry после timeout без readback внешнего operation/status.
5. **Высокий — ложная сдача:** локальный `done` при отсутствии внешнего scan/acceptance/act confirmation.
6. **Высокий — непринимаемая этикетка:** смешение product, posting, package, carriage и cargo codes либо печать неактуального asset.
7. **Высокий — потеря заказов:** reliance только на push либо неправильная пагинация v4 list.
8. **Высокий — регресс WB:** переписывание действующих WB моделей «под универсальность» до появления contract tests и миграционного слоя.
9. **Средний/высокий — дрейф API:** уже объявленные отключения 31 августа 2026 года и частые изменения beta-методов.
10. **Средний — compliance:** необработанные TN VED/marking/IMEI/weight/country requirements блокируют ship или приёмку.
11. **Средний — секреты и expiry:** шестимесячный срок ключа требует безопасного lifecycle, но управление ключами не разрешено этим поручением.

## Конкретная передача архитектору

До прототипа архитектор должен принять и письменно зафиксировать следующие решения. В этом досье они намеренно не приняты за ведущего.

1. **Identity boundary:** что является `marketplace_account`, как оно связано с tenant/seller и как исключается пересечение кабинетов.
2. **Auth modes:** прямой `Client-Id` + `Api-Key`, OAuth private/app-store или оба; модель roles, expiry, health и reconnect без показа секретов.
3. **Write capability:** явный allowlist мутирующих возможностей. `OZON_FBS_STOCK_WRITE` должен отсутствовать/быть deny-by-default на уровне adapter/job/API, а не только UI.
4. **External identifiers:** account-scoped таблица offer/product/sku/barcode и правила сопоставления с WMS SKU, включая неоднозначность и unlink history.
5. **Fulfilment aggregate:** границы order, posting, line, unit/exemplar, package, carriage, FBO supply, cargo и transport cargo; способ миграции без изменения действующих WB таблиц на первом шаге.
6. **Dual lifecycle:** отдельно хранить raw external status/substatus/available_actions и нормализованный WMS workflow; определить terminal/recoverable states.
7. **FBS handover capabilities:** как выбирается one-by-one, carriage, trusted acceptance, pickup/courier, act/pass; ни один вариант не считать универсальным.
8. **FBO workflow:** как моделируются draft operation, timeslot, supply order, content, cargo/TGM, labels, handover, acceptance act и stock appearance.
9. **Marking contract:** unit-level identifiers, validate/set/status, immutable audit trail, correction window, связь с WMS ЧЗ без WB `required_meta` assumptions.
10. **Print/document taxonomy:** asset kind, marketplace/account provenance, source API/version, task id, checksum, dimensions, expiry/supersession и операторское подтверждение печати.
11. **Sync design:** push receiver + signed/validated ingress, poll/reconcile cadence, per-resource versioned checkpoint, backfill и duplicate/out-of-order handling.
12. **Operation ledger:** intent fingerprint, external task/operation id, readback-before-retry, rate-limit state, dead-letter/manual recovery и operator-visible reason.
13. **Errors:** нормализация auth/permission/rate-limit/validation/state-conflict/async-failure без потери оригинального Ozon code/message.
14. **Returns:** отдельный inbound aggregate с исходным posting/line/exemplar, return barcode/pass, inspection outcome и inventory disposition.
15. **Catalog scope:** import-only на первом вертикальном срезе или отдельно gated product publish; product write и stock write не объединять.
16. **Coexistence with WB:** adapter boundary, feature flags per account, isolated routes/jobs/tables, сохранение существующих WB tests как regression gate.
17. **Prototype evidence:** version-frozen official schema, полный read-only credential pair, sanitized fixture corpus для multi-item/marking/split/cancel/returns/FBO cargo, emulator и негативные тесты «stock write impossible».
18. **Release gates:** отдельно доказать local tests, commit/push, deployment SHA и живую browser product acceptance; это исследование не является `PRODUCT_APPROVED_FOR_DEV` или `PRODUCT_BROWSER_APPROVED`.

### Рекомендуемый следующий исследовательский вход для архитектора

Без запроса решений у владельца сейчас можно безопасно подготовить architecture call с двумя обязательными приложениями: (1) зафиксированный OpenAPI/operation matrix на дату проектирования; (2) sanitized read-only capability snapshot тестового кабинета, но только после появления `Client-Id` рядом с уже найденным Api-Key. До этого любые выводы о включённых складах, способах сдачи, ролях и форматах документов должны оставаться неизвестными.

## Проверка соблюдения границ

- Production-код и итоговый UI не проектировались и не изменялись.
- Значение credential не читалось и не печаталось.
- Страницы управления ключами/секретами не открывались.
- Ozon API не вызывался из-за отсутствия полной пары `Client-Id` + `Api-Key`.
- FBS stock, товары, postings, supplies, acts, webhooks и настройки Ozon не создавались и не изменялись.
- Все предложения выше являются передачей вопросов/решений архитектору, а не разрешением на реализацию.
