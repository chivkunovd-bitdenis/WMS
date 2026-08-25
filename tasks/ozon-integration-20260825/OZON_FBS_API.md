# Ozon FBS API — точная выписка OpenAPI

Источник: [https://docs.ozon.ru/api/seller/swagger.json](https://docs.ozon.ru/api/seller/swagger.json) (локальный снимок `OZON_FBS_OPENAPI.json`).
Дата снимка: **25.08.2026**.
OpenAPI: `3.0.0`; title: `Документация Ozon Seller API`; version: `2.1`.
SHA-256 входного JSON: `a1f802b5a1255166144ceecb10713ac850d69427c4ab266296a57e5288ee30a9`.

Этот файл генерируется командой `python3 scripts/generate_ozon_fbs_api_md.py`. Проверка соответствия JSON: `python3 scripts/generate_ozon_fbs_api_md.py --check`.

## Состав

- Методов: **24**.
- Транзитивно достижимых схем: **160** из **160** компонентов.
- В снимке `Client-Id` и `Api-Key` перечислены ссылками в параметрах 21 метода. Их определения (`components.parameters`) в самом JSON отсутствуют, поэтому тип и requiredness не добавлены от себя.
- В трёх методах параметры вовсе не перечислены в источнике: `CarriageGet`, `PostingAPI_ListCountryProductFbsPostingV2`, `PostingAPI_SetCountryProductFbsPostingV2`.
- `Required: нет` означает необязательное поле. `Nullable: нет` означает, что `nullable: true` в исходной схеме отсутствует.

## Методы

### CarriageAPI_CarriageApprove

- HTTP: `POST /v1/carriage/approve`
- operationId: `CarriageAPI_CarriageApprove`
- Summary: Подтверждение отгрузки
- Description: <br>Используйте метод, чтобы подтвердить отгрузку после её создания.<br>После подтверждения отгрузка перейдёт в статус «Сформирована».<br><br>После подтверждения отгрузки вы можете получить лист отгрузки методом [/v2/posting/fbs/act/get-pdf](#operation/PostingAPI_PostingFBSGetAct) и штрихкод отгрузки методом [/v2/posting/fbs/act/get-barcode](#operation/PostingAPI_PostingFBSGetBarcode). <br>
- Tags: `DeliveryFBS`

#### Параметры

| Где | Имя | Обязательный | Тип | Nullable | Описание |
| --- | --- | --- | --- | --- | --- |
| header | `Client-Id` | не указано | unspecified | нет | Исходная ссылка #/components/parameters/Client-Id не разрешается: components.parameters отсутствует в снимке. |
| header | `Api-Key` | не указано | unspecified | нет | Исходная ссылка #/components/parameters/Api-Key не разрешается: components.parameters отсутствует в снимке. |

#### Request body

Обязательный: **да**.
- `application/json`: [`v1CarriageApproveRequest`](#schema-v1carriageapproverequest)

#### Responses

| Status | Описание | Content / schema |
| --- | --- | --- |
| `200` | Отгрузка подтверждена | `application/json`: [`v1CarriageApproveResponse`](#schema-v1carriageapproveresponse) |
| `400` | Неверный параметр | `application/json`: [`rpcStatus`](#schema-rpcstatus) |
| `403` | Доступ запрещён | `application/json`: [`rpcStatus`](#schema-rpcstatus) |
| `404` | Ответ не найден | `application/json`: [`rpcStatus`](#schema-rpcstatus) |
| `409` | Конфликт запроса | `application/json`: [`rpcStatus`](#schema-rpcstatus) |
| `500` | Внутренняя ошибка сервера | `application/json`: [`rpcStatus`](#schema-rpcstatus) |

### CarriageAPI_CarriageCreate

- HTTP: `POST /v1/carriage/create`
- operationId: `CarriageAPI_CarriageCreate`
- Summary: Создание отгрузки
- Description: <br><aside class="warning"><br>Если вы продавец не из России, обратите внимание на доступность <a href="https://seller-edu.ozon.ru/fbs/ozon-logistika/sobrat-zakazy#шаг-2-сформируите-отгрузку">рекомендованного времени</a> в личном кабинете.<br></aside><br><br>Используйте метод для создания первой FBS отгрузки. В неё попадут все отправления со статусом «Готов к отгрузке». Созданная отгрузка получит статус `new`.<br><br>Для отгрузки в статусе `new` можно перезаписать состав отправлений методом [/v1/carriage/set-postings](#operation/CarriageAPI_SetPostings). Если из отгрузки исключить часть отправлений, они могут попасть в следующую отгрузку. <br><br>Чтобы получить список отправлений в отгрузке, используйте метод [/v2/posting/fbs/act/get-postings](#operation/PostingAPI_ActPostingList).<br>
- Tags: `DeliveryFBS`

#### Параметры

| Где | Имя | Обязательный | Тип | Nullable | Описание |
| --- | --- | --- | --- | --- | --- |
| header | `Client-Id` | не указано | unspecified | нет | Исходная ссылка #/components/parameters/Client-Id не разрешается: components.parameters отсутствует в снимке. |
| header | `Api-Key` | не указано | unspecified | нет | Исходная ссылка #/components/parameters/Api-Key не разрешается: components.parameters отсутствует в снимке. |

#### Request body

Обязательный: **да**.
- `application/json`: [`v1CarriageCreateRequest`](#schema-v1carriagecreaterequest)

#### Responses

| Status | Описание | Content / schema |
| --- | --- | --- |
| `200` | Информация об отгрузке | `application/json`: [`v1CarriageCreateResponse`](#schema-v1carriagecreateresponse) |
| `400` | Неверный параметр | `application/json`: [`rpcStatus`](#schema-rpcstatus) |
| `403` | Доступ запрещён | `application/json`: [`rpcStatus`](#schema-rpcstatus) |
| `404` | Ответ не найден | `application/json`: [`rpcStatus`](#schema-rpcstatus) |
| `409` | Конфликт запроса | `application/json`: [`rpcStatus`](#schema-rpcstatus) |
| `500` | Внутренняя ошибка сервера | `application/json`: [`rpcStatus`](#schema-rpcstatus) |

### CarriageGet

- HTTP: `POST /v1/carriage/get`
- operationId: `CarriageGet`
- Summary: Информация о перевозке
- Tags: `DeliveryFBS`

#### Параметры

| Где | Имя | Обязательный | Тип | Nullable | Описание |
| --- | --- | --- | --- | --- | --- |
| — | — | — | — | — | — |

#### Request body

Обязательный: **да**.
- `application/json`: [`carriageCarriageGetRequest`](#schema-carriagecarriagegetrequest)

#### Responses

| Status | Описание | Content / schema |
| --- | --- | --- |
| `200` | Информация о перевозке | `application/json`: [`carriageCarriageGetResponse`](#schema-carriagecarriagegetresponse) |
| `default` | Ошибка | `application/json`: [`rpcStatus`](#schema-rpcstatus) |

### CarriageAPI_SetPostings

- HTTP: `POST /v1/carriage/set-postings`
- operationId: `CarriageAPI_SetPostings`
- Summary: Изменение состава отгрузки
- Description: <br><aside class="warning"><br>Метод недоступен для продавцов из СНГ. <br><br><br>Полностью перезаписывает список заказов в отгрузке. Передавайте только те заказы, которые находятся в статусе <code>Ожидает отгрузки</code>, и вы готовы их отгрузить.    <br><br>Менять состав можно только у отгрузок со статусом `new`.<br></aside><br><br><br><br><br><aside class="notice"><br>Чтобы вернуться к списку заказов, удалите отгрузку с помощью метода <a href="#operation/CarriageAPI_CarriageCancel">/v1/carriage/cancel</a>, и создайте новую.<br></aside><br>
- Tags: `DeliveryFBS`

#### Параметры

| Где | Имя | Обязательный | Тип | Nullable | Описание |
| --- | --- | --- | --- | --- | --- |
| header | `Client-Id` | не указано | unspecified | нет | Исходная ссылка #/components/parameters/Client-Id не разрешается: components.parameters отсутствует в снимке. |
| header | `Api-Key` | не указано | unspecified | нет | Исходная ссылка #/components/parameters/Api-Key не разрешается: components.parameters отсутствует в снимке. |

#### Request body

Обязательный: **да**.
- `application/json`: [`v1SetPostingsRequest`](#schema-v1setpostingsrequest)

#### Responses

| Status | Описание | Content / schema |
| --- | --- | --- |
| `200` | Информация об отправлении | `application/json`: [`v1SetPostingsResponse`](#schema-v1setpostingsresponse) |
| `400` | Неверный параметр | `application/json`: [`rpcStatus`](#schema-rpcstatus) |
| `403` | Доступ запрещён | `application/json`: [`rpcStatus`](#schema-rpcstatus) |
| `404` | Ответ не найден | `application/json`: [`rpcStatus`](#schema-rpcstatus) |
| `409` | Конфликт запроса | `application/json`: [`rpcStatus`](#schema-rpcstatus) |
| `500` | Внутренняя ошибка сервера | `application/json`: [`rpcStatus`](#schema-rpcstatus) |

### PostingAPI_GetLabelBatch

- HTTP: `POST /v1/posting/fbs/package-label/get`
- operationId: `PostingAPI_GetLabelBatch`
- Summary: Получить файл с этикетками
- Description: Метод для получения этикеток после вызова [/v1/posting/fbs/package-label/create](#operation/PostingAPI_CreateLabelBatch).
- Tags: `FBS`

#### Параметры

| Где | Имя | Обязательный | Тип | Nullable | Описание |
| --- | --- | --- | --- | --- | --- |
| header | `Client-Id` | не указано | unspecified | нет | Исходная ссылка #/components/parameters/Client-Id не разрешается: components.parameters отсутствует в снимке. |
| header | `Api-Key` | не указано | unspecified | нет | Исходная ссылка #/components/parameters/Api-Key не разрешается: components.parameters отсутствует в снимке. |

#### Request body

Обязательный: **да**.
- `application/json`: [`v1GetLabelBatchRequest`](#schema-v1getlabelbatchrequest)

#### Responses

| Status | Описание | Content / schema |
| --- | --- | --- |
| `200` | Статус формирования этикеток или файл с ними | `application/json`: [`v1GetLabelBatchResponse`](#schema-v1getlabelbatchresponse) |
| `400` | Неверный параметр | `application/json`: [`rpcStatus`](#schema-rpcstatus) |
| `403` | Доступ запрещён | `application/json`: [`rpcStatus`](#schema-rpcstatus) |
| `404` | Ответ не найден | `application/json`: [`rpcStatus`](#schema-rpcstatus) |
| `409` | Конфликт запроса | `application/json`: [`rpcStatus`](#schema-rpcstatus) |
| `500` | Внутренняя ошибка сервера | `application/json`: [`rpcStatus`](#schema-rpcstatus) |

### PostingAPI_GetRestrictions

- HTTP: `POST /v1/posting/fbs/restrictions`
- operationId: `PostingAPI_GetRestrictions`
- Summary: Получить ограничения пункта приёма
- Description: Метод для получения габаритных, весовых и прочих ограничений пункта приёма по номеру отправления. Метод применим только для работы по схеме FBS.
- Tags: `FBS`

#### Параметры

| Где | Имя | Обязательный | Тип | Nullable | Описание |
| --- | --- | --- | --- | --- | --- |
| header | `Client-Id` | не указано | unspecified | нет | Исходная ссылка #/components/parameters/Client-Id не разрешается: components.parameters отсутствует в снимке. |
| header | `Api-Key` | не указано | unspecified | нет | Исходная ссылка #/components/parameters/Api-Key не разрешается: components.parameters отсутствует в снимке. |

#### Request body

Обязательный: **да**.
- `application/json`: [`v1GetRestrictionsRequest`](#schema-v1getrestrictionsrequest)

#### Responses

| Status | Описание | Content / schema |
| --- | --- | --- |
| `200` | Ограничения пункта приёма | `application/json`: [`v1GetRestrictionsResponse`](#schema-v1getrestrictionsresponse) |
| `400` | Неверный параметр | `application/json`: [`rpcStatus`](#schema-rpcstatus) |
| `403` | Доступ запрещён | `application/json`: [`rpcStatus`](#schema-rpcstatus) |
| `404` | Ответ не найден | `application/json`: [`rpcStatus`](#schema-rpcstatus) |
| `409` | Конфликт запроса | `application/json`: [`rpcStatus`](#schema-rpcstatus) |
| `500` | Внутренняя ошибка сервера | `application/json`: [`rpcStatus`](#schema-rpcstatus) |

### PostingAPI_PostingFBSGetBarcode

- HTTP: `POST /v2/posting/fbs/act/get-barcode`
- operationId: `PostingAPI_PostingFBSGetBarcode`
- Summary: Штрихкод для отгрузки отправления
- Description: Метод для получения штрихкода, который нужно показать в пункте выдачи или сортировочном центре при отгрузке отправления.
- Tags: `DeliveryFBS`

#### Параметры

| Где | Имя | Обязательный | Тип | Nullable | Описание |
| --- | --- | --- | --- | --- | --- |
| header | `Client-Id` | не указано | unspecified | нет | Исходная ссылка #/components/parameters/Client-Id не разрешается: components.parameters отсутствует в снимке. |
| header | `Api-Key` | не указано | unspecified | нет | Исходная ссылка #/components/parameters/Api-Key не разрешается: components.parameters отсутствует в снимке. |

#### Request body

Обязательный: **да**.
- `application/json`: [`v2PostingFBSGetBarcodeRequest`](#schema-v2postingfbsgetbarcoderequest)

#### Responses

| Status | Описание | Content / schema |
| --- | --- | --- |
| `200` | Штрихкод для отправления | `image/png`: [`v2PostingFBSGetBarcodeResponse`](#schema-v2postingfbsgetbarcoderesponse) |
| `400` | Неверный параметр | `application/json`: [`rpcStatus`](#schema-rpcstatus) |
| `403` | Доступ запрещён | `application/json`: [`rpcStatus`](#schema-rpcstatus) |
| `404` | Ответ не найден | `application/json`: [`rpcStatus`](#schema-rpcstatus) |
| `409` | Конфликт запроса | `application/json`: [`rpcStatus`](#schema-rpcstatus) |
| `500` | Внутренняя ошибка сервера | `application/json`: [`rpcStatus`](#schema-rpcstatus) |

### PostingAPI_PostingFBSGetBarcodeText

- HTTP: `POST /v2/posting/fbs/act/get-barcode/text`
- operationId: `PostingAPI_PostingFBSGetBarcodeText`
- Summary: Значение штрихкода для отгрузки отправления
- Description: Используйте этот метод, чтобы получить штрихкод из ответа<br>[/v2/posting/fbs/act/get-barcode](#operation/PostingAPI_PostingFBSGetBarcode) в текстовом виде.<br>
- Tags: `DeliveryFBS`

#### Параметры

| Где | Имя | Обязательный | Тип | Nullable | Описание |
| --- | --- | --- | --- | --- | --- |
| header | `Client-Id` | не указано | unspecified | нет | Исходная ссылка #/components/parameters/Client-Id не разрешается: components.parameters отсутствует в снимке. |
| header | `Api-Key` | не указано | unspecified | нет | Исходная ссылка #/components/parameters/Api-Key не разрешается: components.parameters отсутствует в снимке. |

#### Request body

Обязательный: **нет**.
- `application/json`: [`v2PostingFBSGetBarcodeRequest`](#schema-v2postingfbsgetbarcoderequest)

#### Responses

| Status | Описание | Content / schema |
| --- | --- | --- |
| `200` | Значение штрихкода | `application/json`: [`v2PostingFBSGetBarcodeTextResponse`](#schema-v2postingfbsgetbarcodetextresponse) |
| `default` | Ошибка | `application/json`: [`rpcStatus`](#schema-rpcstatus) |

### PostingAPI_MoveFbsPostingToAwaitingDelivery

- HTTP: `POST /v2/posting/fbs/awaiting-delivery`
- operationId: `PostingAPI_MoveFbsPostingToAwaitingDelivery`
- Summary: Передать отправление к отгрузке
- Description: Передает спорные заказы к отгрузке. Статус отправления изменится на `awaiting_deliver`.
- Tags: `FBS`

#### Параметры

| Где | Имя | Обязательный | Тип | Nullable | Описание |
| --- | --- | --- | --- | --- | --- |
| header | `Client-Id` | не указано | unspecified | нет | Исходная ссылка #/components/parameters/Client-Id не разрешается: components.parameters отсутствует в снимке. |
| header | `Api-Key` | не указано | unspecified | нет | Исходная ссылка #/components/parameters/Api-Key не разрешается: components.parameters отсутствует в снимке. |

#### Request body

Обязательный: **нет**.
- `application/json`: [`v2MovePostingToAwaitingDeliveryRequest`](#schema-v2movepostingtoawaitingdeliveryrequest)

#### Responses

| Status | Описание | Content / schema |
| --- | --- | --- |
| `200` | Отправление передано к отгрузке | `application/json`: [`postingBooleanResponse`](#schema-postingbooleanresponse) |
| `400` | Неверный параметр | `application/json`: [`rpcStatus`](#schema-rpcstatus) |
| `403` | Доступ запрещён | `application/json`: [`rpcStatus`](#schema-rpcstatus) |
| `404` | Ответ не найден | `application/json`: [`rpcStatus`](#schema-rpcstatus) |
| `409` | Конфликт запроса | `application/json`: [`rpcStatus`](#schema-rpcstatus) |
| `500` | Внутренняя ошибка сервера | `application/json`: [`rpcStatus`](#schema-rpcstatus) |

### PostingAPI_PostingFBSGetDigitalAct

- HTTP: `POST /v2/posting/fbs/digital/act/get-pdf`
- operationId: `PostingAPI_PostingFBSGetDigitalAct`
- Summary: Получить лист отгрузки по перевозке
- Description: <aside class="warning"><br>Метод устаревает и будет отключён 22 марта 2026 года. Переключитесь на <a href="#operation/PostingAPI_PostingFBSGetAct">/v2/posting/fbs/act/get-pdf</a>.<br></aside><br><br>Вы можете получить документы, если в ответе метода [/v2/posting/fbs/digital/act/check-status](#operation/PostingAPI_PostingFBSDigitalActCheckStatus) был один из статусов:<br>- `FORMED` — перевозка сформирована успешно,<br>- `CONFIRMED` — перевозка подтверждена Ozon,<br>- `CONFIRMED_WITH_MISMATCH` — перевозка принята Ozon с расхождениями.<br>
- Tags: `DeliveryFBS`

#### Параметры

| Где | Имя | Обязательный | Тип | Nullable | Описание |
| --- | --- | --- | --- | --- | --- |
| header | `Client-Id` | не указано | unspecified | нет | Исходная ссылка #/components/parameters/Client-Id не разрешается: components.parameters отсутствует в снимке. |
| header | `Api-Key` | не указано | unspecified | нет | Исходная ссылка #/components/parameters/Api-Key не разрешается: components.parameters отсутствует в снимке. |

#### Request body

Обязательный: **да**.
- `application/json`: [`v2PostingFBSGetDigitalActRequest`](#schema-v2postingfbsgetdigitalactrequest)

#### Responses

| Status | Описание | Content / schema |
| --- | --- | --- |
| `200` | Файл с документом | `application/pdf`: [`v2PostingFBSGetDigitalActResponse`](#schema-v2postingfbsgetdigitalactresponse) |
| `400` | Неверный параметр | `application/json`: [`rpcStatus`](#schema-rpcstatus) |
| `403` | Доступ запрещён | `application/json`: [`rpcStatus`](#schema-rpcstatus) |
| `404` | Ответ не найден | `application/json`: [`rpcStatus`](#schema-rpcstatus) |
| `409` | Конфликт запроса | `application/json`: [`rpcStatus`](#schema-rpcstatus) |
| `500` | Внутренняя ошибка сервера | `application/json`: [`rpcStatus`](#schema-rpcstatus) |

### PostingAPI_PostingFBSPackageLabel

- HTTP: `POST /v2/posting/fbs/package-label`
- operationId: `PostingAPI_PostingFBSPackageLabel`
- Summary: Напечатать этикетку
- Description: <aside class="warning"><br>Если вы работаете по схеме rFBS или rFBS Express, изучите процесс печати этикетки в <a href="https://seller-edu.ozon.ru/rfbs/scheme-of-work">Базе знаний продавца</a>.<br></aside><br><br>Генерирует PDF-файл с этикетками для указанных отправлений в статусе «Ожидает отгрузки» — `awaiting_deliver`. В одном запросе можно передать не больше 20 идентификаторов. Если хотя бы для одного отправления возникнет ошибка, этикетки не будут подготовлены для всех отправлений в запросе.<br><br>Рекомендуем запрашивать этикетки через 45–60 секунд после сборки заказа.<br><br>Ошибка `The next postings aren't ready` означает, что этикетки ещё не готовы, повторите запрос позднее.<br>
- Tags: `FBS`

#### Параметры

| Где | Имя | Обязательный | Тип | Nullable | Описание |
| --- | --- | --- | --- | --- | --- |
| header | `Client-Id` | не указано | unspecified | нет | Исходная ссылка #/components/parameters/Client-Id не разрешается: components.parameters отсутствует в снимке. |
| header | `Api-Key` | не указано | unspecified | нет | Исходная ссылка #/components/parameters/Api-Key не разрешается: components.parameters отсутствует в снимке. |

#### Request body

Обязательный: **да**.
- `application/json`: [`postingPostingFBSPackageLabelRequest`](#schema-postingpostingfbspackagelabelrequest)

#### Responses

| Status | Описание | Content / schema |
| --- | --- | --- |
| `200` | Маркировка напечатана | `application/pdf`: [`postingPostingFBSPackageLabelResponse`](#schema-postingpostingfbspackagelabelresponse) |
| `400` | Неверный параметр | `application/json`: [`rpcStatus`](#schema-rpcstatus) |
| `403` | Доступ запрещён | `application/json`: [`rpcStatus`](#schema-rpcstatus) |
| `404` | Ответ не найден | `application/json`: [`rpcStatus`](#schema-rpcstatus) |
| `409` | Конфликт запроса | `application/json`: [`rpcStatus`](#schema-rpcstatus) |
| `500` | Внутренняя ошибка сервера | `application/json`: [`rpcStatus`](#schema-rpcstatus) |

### PostingAPI_CreateLabelBatchV2

- HTTP: `POST /v2/posting/fbs/package-label/create`
- operationId: `PostingAPI_CreateLabelBatchV2`
- Summary: Создать задание на формирование этикеток
- Description: <aside class="warning"><br>Если вы работаете по схеме rFBS или rFBS Express, изучите процесс печати этикетки в <a href="https://seller-edu.ozon.ru/rfbs/scheme-of-work">Базе знаний продавца</a>.<br></aside><br><br>Метод для создания задания на асинхронное формирование этикеток для отправлений в статусе «Ожидает отгрузки» — `awaiting_deliver`.<br>Метод может вернуть несколько заданий: на формирование маленькой и большой этикетки.<br><br>Рекомендуем запрашивать этикетки через 45–60 секунд после сборки заказа.<br><br>Чтобы получить созданные этикетки, используйте [/v1/posting/fbs/package-label/get](#operation/PostingAPI_GetLabelBatch).<br>
- Tags: `FBS`

#### Параметры

| Где | Имя | Обязательный | Тип | Nullable | Описание |
| --- | --- | --- | --- | --- | --- |
| header | `Client-Id` | не указано | unspecified | нет | Исходная ссылка #/components/parameters/Client-Id не разрешается: components.parameters отсутствует в снимке. |
| header | `Api-Key` | не указано | unspecified | нет | Исходная ссылка #/components/parameters/Api-Key не разрешается: components.parameters отсутствует в снимке. |

#### Request body

Обязательный: **да**.
- `application/json`: [`v1CreateLabelBatchRequest`](#schema-v1createlabelbatchrequest)

#### Responses

| Status | Описание | Content / schema |
| --- | --- | --- |
| `200` | Задания на формирование этикеток | `application/json`: [`v2CreateLabelBatchResponse`](#schema-v2createlabelbatchresponse) |
| `400` | Неверный параметр | `application/json`: [`rpcStatus`](#schema-rpcstatus) |
| `403` | Доступ запрещён | `application/json`: [`rpcStatus`](#schema-rpcstatus) |
| `404` | Ответ не найден | `application/json`: [`rpcStatus`](#schema-rpcstatus) |
| `409` | Конфликт запроса | `application/json`: [`rpcStatus`](#schema-rpcstatus) |
| `500` | Внутренняя ошибка сервера | `application/json`: [`rpcStatus`](#schema-rpcstatus) |

### PostingAPI_ListCountryProductFbsPostingV2

- HTTP: `POST /v2/posting/fbs/product/country/list`
- operationId: `PostingAPI_ListCountryProductFbsPostingV2`
- Summary: Список доступных стран-изготовителей
- Description: Метод для получения списка доступных стран-изготовителей и их ISO кодов.
- Tags: `FBS`

#### Параметры

| Где | Имя | Обязательный | Тип | Nullable | Описание |
| --- | --- | --- | --- | --- | --- |
| — | — | — | — | — | — |

#### Request body

Обязательный: **да**.
- `application/json`: [`v2FbsPostingProductCountryListRequest`](#schema-v2fbspostingproductcountrylistrequest)

#### Responses

| Status | Описание | Content / schema |
| --- | --- | --- |
| `200` | Список доступных стран-изготовителей | `application/json`: [`v2FbsPostingProductCountryListResponse`](#schema-v2fbspostingproductcountrylistresponse) |
| `default` | Ошибка | `application/json`: [`googlerpcStatus`](#schema-googlerpcstatus) |

### PostingAPI_SetCountryProductFbsPostingV2

- HTTP: `POST /v2/posting/fbs/product/country/set`
- operationId: `PostingAPI_SetCountryProductFbsPostingV2`
- Summary: Добавить информацию о стране-изготовителе товара
- Description: Метод для добавления на продукт атрибута «Страна-изготовитель», если он не был указан.
- Tags: `FBS`

#### Параметры

| Где | Имя | Обязательный | Тип | Nullable | Описание |
| --- | --- | --- | --- | --- | --- |
| — | — | — | — | — | — |

#### Request body

Обязательный: **да**.
- `application/json`: [`v2FbsPostingProductCountrySetRequest`](#schema-v2fbspostingproductcountrysetrequest)

#### Responses

| Status | Описание | Content / schema |
| --- | --- | --- |
| `200` | Страна-изготовитель добавлена | `application/json`: [`v2FbsPostingProductCountrySetResponse`](#schema-v2fbspostingproductcountrysetresponse) |
| `default` | Ошибка | `application/json`: [`googlerpcStatus`](#schema-googlerpcstatus) |

### PostingAPI_GetFbsPostingV3

- HTTP: `POST /v3/posting/fbs/get`
- operationId: `PostingAPI_GetFbsPostingV3`
- Summary: Получить информацию об отправлении по идентификатору
- Description: Чтобы получать актуальную дату отгрузки, регулярно обновляйте информацию об отправлениях или подключите [пуш-уведомления](#tag/push_start).
- Tags: `FBS`

#### Параметры

| Где | Имя | Обязательный | Тип | Nullable | Описание |
| --- | --- | --- | --- | --- | --- |
| header | `Client-Id` | не указано | unspecified | нет | Исходная ссылка #/components/parameters/Client-Id не разрешается: components.parameters отсутствует в снимке. |
| header | `Api-Key` | не указано | unspecified | нет | Исходная ссылка #/components/parameters/Api-Key не разрешается: components.parameters отсутствует в снимке. |

#### Request body

Обязательный: **да**.
- `application/json`: [`postingv3GetFbsPostingRequest`](#schema-postingv3getfbspostingrequest)

#### Responses

| Status | Описание | Content / schema |
| --- | --- | --- |
| `200` | Информация об отправлении | `application/json`: [`v3GetFbsPostingResponseV3`](#schema-v3getfbspostingresponsev3) |
| `400` | Неверный параметр | `application/json`: [`rpcStatus`](#schema-rpcstatus) |
| `403` | Доступ запрещён | `application/json`: [`rpcStatus`](#schema-rpcstatus) |
| `404` | Ответ не найден | `application/json`: [`rpcStatus`](#schema-rpcstatus) |
| `409` | Конфликт запроса | `application/json`: [`rpcStatus`](#schema-rpcstatus) |
| `500` | Внутренняя ошибка сервера | `application/json`: [`rpcStatus`](#schema-rpcstatus) |

### PostingAPI_PostingMultiBoxQtySetV3

- HTTP: `POST /v3/posting/multiboxqty/set`
- operationId: `PostingAPI_PostingMultiBoxQtySetV3`
- Summary: Указать количество коробок для многокоробочных отправлений
- Description: Метод для передачи количества коробок для отправлений, в которых есть многокоробочные товары.<br><br>Используйте метод при работе по схеме rFBS Агрегатор — c доставкой партнёрами Ozon.<br>
- Tags: `FBS`

#### Параметры

| Где | Имя | Обязательный | Тип | Nullable | Описание |
| --- | --- | --- | --- | --- | --- |
| header | `Client-Id` | не указано | unspecified | нет | Исходная ссылка #/components/parameters/Client-Id не разрешается: components.parameters отсутствует в снимке. |
| header | `Api-Key` | не указано | unspecified | нет | Исходная ссылка #/components/parameters/Api-Key не разрешается: components.parameters отсутствует в снимке. |

#### Request body

Обязательный: **да**.
- `application/json`: [`postingv3PostingMultiBoxQtySetV3Request`](#schema-postingv3postingmultiboxqtysetv3request)

#### Responses

| Status | Описание | Content / schema |
| --- | --- | --- |
| `200` | Количество коробок указано | `application/json`: [`postingv3PostingMultiBoxQtySetV3Response`](#schema-postingv3postingmultiboxqtysetv3response) |
| `400` | Неверный параметр | `application/json`: [`rpcStatus`](#schema-rpcstatus) |
| `403` | Доступ запрещён | `application/json`: [`rpcStatus`](#schema-rpcstatus) |
| `404` | Ответ не найден | `application/json`: [`rpcStatus`](#schema-rpcstatus) |
| `409` | Конфликт запроса | `application/json`: [`rpcStatus`](#schema-rpcstatus) |
| `500` | Внутренняя ошибка сервера | `application/json`: [`rpcStatus`](#schema-rpcstatus) |

### PostingFbsList

- HTTP: `POST /v4/posting/fbs/list`
- operationId: `PostingFbsList`
- Summary: Получить список отправлений
- Description: Возвращает список отправлений за указанный период времени — он должен быть не больше одного года.<br><br> Чтобы получать актуальную дату отгрузки, регулярно обновляйте информацию об отправлениях или подключите [пуш-уведомления](#tag/push_start).<br>
- Tags: `FBS`

#### Параметры

| Где | Имя | Обязательный | Тип | Nullable | Описание |
| --- | --- | --- | --- | --- | --- |
| header | `Client-Id` | не указано | unspecified | нет | Исходная ссылка #/components/parameters/Client-Id не разрешается: components.parameters отсутствует в снимке. |
| header | `Api-Key` | не указано | unspecified | нет | Исходная ссылка #/components/parameters/Api-Key не разрешается: components.parameters отсутствует в снимке. |

#### Request body

Обязательный: **да**.
- `application/json`: [`posting.v4.PostingFbsListRequest`](#schema-posting-v4-postingfbslistrequest)

#### Responses

| Status | Описание | Content / schema |
| --- | --- | --- |
| `200` | Список отправлений | `application/json`: [`posting.v4.PostingFbsListResponse`](#schema-posting-v4-postingfbslistresponse) |
| `400` | Неверный параметр | `application/json`: [`rpcStatus`](#schema-rpcstatus) |
| `403` | Доступ запрещён | `application/json`: [`rpcStatus`](#schema-rpcstatus) |
| `404` | Ответ не найден | `application/json`: [`rpcStatus`](#schema-rpcstatus) |
| `409` | Конфликт запроса | `application/json`: [`rpcStatus`](#schema-rpcstatus) |
| `500` | Внутренняя ошибка сервера | `application/json`: [`rpcStatus`](#schema-rpcstatus) |

### PostingAPI_ShipFbsPostingV4

- HTTP: `POST /v4/posting/fbs/ship`
- operationId: `PostingAPI_ShipFbsPostingV4`
- Summary: Собрать заказ (версия 4)
- Description: <aside class="warning"><br>Ответ с кодом <tt>200</tt> не гарантирует успешную сборку заказа. Используйте метод <a href="#operation/PostingAPI_GetFbsPostingV3">/v3/posting/fbs/get</a>, чтобы проверить, что заказ собран. Если в ответе указан <tt>result.substatus = ship_failed</tt>, повторите сборку заказа.<br></aside><br><br>Делит заказ на отправления и переводит его в статус `awaiting_deliver`.<br><br>Каждый элемент в `packages` может содержать несколько элементов `products` или отправлений. <br>Каждый элемент в `products` — это товар, включённый в данное отправление.<br><br>Разделить заказ нужно, если:<br>  - товары не помещаются в одну упаковку,<br>  - товары нельзя сложить в одну упаковку.<br>  <br>Чтобы разделить заказ, передайте в массиве `packages` несколько объектов.<br><br>Пример запроса, когда заказ разделять не нужно: 2 товара будут в одном отправлении.<br>```<br>{<br>  "packages": [<br>    {<br>      "products": [<br>        {<br>          "product_id": 185479045,<br>          "quantity": 2<br>        }<br>      ]<br>    }<br>  ],<br>  "posting_number": "89491381-0072-1"<br>}<br>```<br><br>Пример запроса, когда заказ нужно разделить: каждый товар будет в отдельном отправлении.<br><br>```<br>{<br>  "packages": [<br>    {<br>      "products": [<br>        {<br>          "product_id": 185479045,<br>          "quantity": 1<br>        }<br>      ]<br>    },<br>    {<br>      "products": [<br>        {<br>          "product_id": 185479045,<br>          "quantity": 1<br>        }<br>      ]<br>    }<br>  ],<br>  "posting_number": "89491381-0072-1"<br>}    <br>```  <br><br>Чтобы внести информацию по экземплярам, используйте метод [/v6/fbs/posting/product/exemplar/set](#operation/PostingAPI_FbsPostingProductExemplarSetV6).<br>
- Tags: `FBS&rFBSMarks`

#### Параметры

| Где | Имя | Обязательный | Тип | Nullable | Описание |
| --- | --- | --- | --- | --- | --- |
| header | `Client-Id` | не указано | unspecified | нет | Исходная ссылка #/components/parameters/Client-Id не разрешается: components.parameters отсутствует в снимке. |
| header | `Api-Key` | не указано | unspecified | нет | Исходная ссылка #/components/parameters/Api-Key не разрешается: components.parameters отсутствует в снимке. |

#### Request body

Обязательный: **да**.
- `application/json`: [`fbsv4FbsPostingShipV4Request`](#schema-fbsv4fbspostingshipv4request)

#### Responses

| Status | Описание | Content / schema |
| --- | --- | --- |
| `200` | Результат сборки заказа | `application/json`: [`fbsv4FbsPostingShipV4Response`](#schema-fbsv4fbspostingshipv4response) |
| `default` | Ошибка | `application/json`: [`rpcStatus`](#schema-rpcstatus) |

### PostingAPI_ShipFbsPostingPackage

- HTTP: `POST /v4/posting/fbs/ship/package`
- operationId: `PostingAPI_ShipFbsPostingPackage`
- Summary: Частичная сборка отправления (версия 4)
- Description: <aside class="warning"><br>Ответ с кодом <tt>200</tt> не гарантирует успешную сборку отправления. Используйте метод <a href="#operation/PostingAPI_GetFbsPostingV3">/v3/posting/fbs/get</a>, чтобы проверить, что отправление собрано. Если в ответе указан <tt>result.substatus = ship_failed</tt>, повторите сборку отправления.<br></aside><br><br>Если в запросе передать часть товаров из отправления, метод разделит первичное отправление на две части. <br>В первичном несобранном отправлении останется часть товаров, которую не передали в запросе.<br><br>По умолчанию статус созданных отправлений `awaiting_packaging` — ожидает сборки.<br><br>Статус изначального отправления изменится только после изменения статуса отправлений, на которые он разделился.<br>
- Tags: `FBS&rFBSMarks`

#### Параметры

| Где | Имя | Обязательный | Тип | Nullable | Описание |
| --- | --- | --- | --- | --- | --- |
| header | `Client-Id` | не указано | unspecified | нет | Исходная ссылка #/components/parameters/Client-Id не разрешается: components.parameters отсутствует в снимке. |
| header | `Api-Key` | не указано | unspecified | нет | Исходная ссылка #/components/parameters/Api-Key не разрешается: components.parameters отсутствует в снимке. |

#### Request body

Обязательный: **да**.
- `application/json`: [`v4FbsPostingShipPackageV4Request`](#schema-v4fbspostingshippackagev4request)

#### Responses

| Status | Описание | Content / schema |
| --- | --- | --- |
| `200` | Результат сборки отправления | `application/json`: [`v4FbsPostingShipPackageV4Response`](#schema-v4fbspostingshippackagev4response) |
| `default` | Ошибка | `application/json`: [`rpcStatus`](#schema-rpcstatus) |

### PostingFbsUnfulfilledList

- HTTP: `POST /v4/posting/fbs/unfulfilled/list`
- operationId: `PostingFbsUnfulfilledList`
- Summary: Получить список необработанных отправлений
- Description: Возвращает список необработанных отправлений за указанный период времени — он должен быть не больше одного года.<br><br>Возможные статусы отправлений:<br>- `awaiting_registration` — ожидает регистрации;<br>- `acceptance_in_progress` — идёт приёмка;<br>- `awaiting_approve` — ожидает подтверждения;<br>- `awaiting_packaging` — ожидает упаковки;<br>- `awaiting_deliver` — ожидает отгрузки;<br>- `arbitration` — арбитраж;<br>- `client_arbitration` — клиентский арбитраж доставки;<br>- `delivering` — доставляется;<br>- `driver_pickup` — у водителя;<br>- `cancelled` — отменено;<br>- `not_accepted` — не принято на сортировочном центре.<br><br>Чтобы получать актуальную дату отгрузки, регулярно обновляйте информацию об отправлениях или подключите [пуш-уведомления](#tag/push_start).<br>
- Tags: `FBS`

#### Параметры

| Где | Имя | Обязательный | Тип | Nullable | Описание |
| --- | --- | --- | --- | --- | --- |
| header | `Client-Id` | не указано | unspecified | нет | Исходная ссылка #/components/parameters/Client-Id не разрешается: components.parameters отсутствует в снимке. |
| header | `Api-Key` | не указано | unspecified | нет | Исходная ссылка #/components/parameters/Api-Key не разрешается: components.parameters отсутствует в снимке. |

#### Request body

Обязательный: **да**.
- `application/json`: [`posting.v4.PostingFbsUnfulfilledListRequest`](#schema-posting-v4-postingfbsunfulfilledlistrequest)

#### Responses

| Status | Описание | Content / schema |
| --- | --- | --- |
| `200` | Список необработанных отправлений | `application/json`: [`posting.v4.PostingFbsUnfulfilledListResponse`](#schema-posting-v4-postingfbsunfulfilledlistresponse) |
| `400` | Неверный параметр | `application/json`: [`rpcStatus`](#schema-rpcstatus) |
| `403` | Доступ запрещён | `application/json`: [`rpcStatus`](#schema-rpcstatus) |
| `404` | Ответ не найден | `application/json`: [`rpcStatus`](#schema-rpcstatus) |
| `409` | Конфликт запроса | `application/json`: [`rpcStatus`](#schema-rpcstatus) |
| `500` | Внутренняя ошибка сервера | `application/json`: [`rpcStatus`](#schema-rpcstatus) |

### PostingAPI_FbsPostingProductExemplarStatusV5

- HTTP: `POST /v5/fbs/posting/product/exemplar/status`
- operationId: `PostingAPI_FbsPostingProductExemplarStatusV5`
- Summary: Получить статус добавления экземпляров
- Description: Метод для получения статусов добавления экземпляров, переданных в методе [/v6/fbs/posting/product/exemplar/set](#operation/PostingAPI_FbsPostingProductExemplarSetV6). Также возвращает данные по этим экземплярам.<br>
- Tags: `FBS&rFBSMarks`

#### Параметры

| Где | Имя | Обязательный | Тип | Nullable | Описание |
| --- | --- | --- | --- | --- | --- |
| header | `Client-Id` | не указано | unspecified | нет | Исходная ссылка #/components/parameters/Client-Id не разрешается: components.parameters отсутствует в снимке. |
| header | `Api-Key` | не указано | unspecified | нет | Исходная ссылка #/components/parameters/Api-Key не разрешается: components.parameters отсутствует в снимке. |

#### Request body

Обязательный: **да**.
- `application/json`: [`v5FbsPostingProductExemplarStatusV5Request`](#schema-v5fbspostingproductexemplarstatusv5request)

#### Responses

| Status | Описание | Content / schema |
| --- | --- | --- |
| `200` | Статусы проверки экземпляров | `application/json`: [`v5FbsPostingProductExemplarStatusV5Response`](#schema-v5fbspostingproductexemplarstatusv5response) |
| `default` | Ошибка | `application/json`: [`rpcStatus`](#schema-rpcstatus) |

### PostingAPI_FbsPostingProductExemplarValidateV5

- HTTP: `POST /v5/fbs/posting/product/exemplar/validate`
- operationId: `PostingAPI_FbsPostingProductExemplarValidateV5`
- Summary: Валидация кодов маркировки
- Description: Метод для проверки кодов на соответствие требованиям системы «Честный ЗНАК» по количеству и составу символов, а также других маркировок.<br><br>Если у вас нет номера грузовой таможенной декларации (ГТД), вы можете его не указывать.<br>
- Tags: `FBS&rFBSMarks`

#### Параметры

| Где | Имя | Обязательный | Тип | Nullable | Описание |
| --- | --- | --- | --- | --- | --- |
| header | `Client-Id` | не указано | unspecified | нет | Исходная ссылка #/components/parameters/Client-Id не разрешается: components.parameters отсутствует в снимке. |
| header | `Api-Key` | не указано | unspecified | нет | Исходная ссылка #/components/parameters/Api-Key не разрешается: components.parameters отсутствует в снимке. |

#### Request body

Обязательный: **да**.
- `application/json`: [`v5FbsPostingProductExemplarValidateV5Request`](#schema-v5fbspostingproductexemplarvalidatev5request)

#### Responses

| Status | Описание | Content / schema |
| --- | --- | --- |
| `200` | Результат валидации | `application/json`: [`v5FbsPostingProductExemplarValidateV5Response`](#schema-v5fbspostingproductexemplarvalidatev5response) |
| `default` | Ошибка | `application/json`: [`rpcStatus`](#schema-rpcstatus) |

### PostingAPI_FbsPostingProductExemplarCreateOrGetV6

- HTTP: `POST /v6/fbs/posting/product/exemplar/create-or-get`
- operationId: `PostingAPI_FbsPostingProductExemplarCreateOrGetV6`
- Summary: Получить данные созданных экземпляров
- Description: Метод для получения информации по экземплярам товаров из отправления, переданных в методе [/v6/fbs/posting/product/exemplar/set](#operation/PostingAPI_FbsPostingProductExemplarSetV6).<br><br>Используйте метод для получения `exemplar_id`.<br>
- Tags: `FBS&rFBSMarks`

#### Параметры

| Где | Имя | Обязательный | Тип | Nullable | Описание |
| --- | --- | --- | --- | --- | --- |
| header | `Client-Id` | не указано | unspecified | нет | Исходная ссылка #/components/parameters/Client-Id не разрешается: components.parameters отсутствует в снимке. |
| header | `Api-Key` | не указано | unspecified | нет | Исходная ссылка #/components/parameters/Api-Key не разрешается: components.parameters отсутствует в снимке. |

#### Request body

Обязательный: **да**.
- `application/json`: [`v6FbsPostingProductExemplarCreateOrGetV6Request`](#schema-v6fbspostingproductexemplarcreateorgetv6request)

#### Responses

| Status | Описание | Content / schema |
| --- | --- | --- |
| `200` | Данные экземпляров | `application/json`: [`v6FbsPostingProductExemplarCreateOrGetV6Response`](#schema-v6fbspostingproductexemplarcreateorgetv6response) |
| `default` | Ошибка | `application/json`: [`rpcStatus`](#schema-rpcstatus) |

### PostingAPI_FbsPostingProductExemplarSetV6

- HTTP: `POST /v6/fbs/posting/product/exemplar/set`
- operationId: `PostingAPI_FbsPostingProductExemplarSetV6`
- Summary: Проверить и сохранить данные экземпляров
- Description: Асинхронный метод:<br>- для проверки наличия экземпляров в обороте в системе «Честный ЗНАК»;<br>- для сохранения данных экземпляров. <br><br>Чтобы получить результаты проверок, используйте метод [/v5/fbs/posting/product/exemplar/status](#operation/PostingAPI_FbsPostingProductExemplarStatusV5). <br>Для получения данных о созданных экземплярах, используйте метод [/v6/fbs/posting/product/exemplar/create-or-get](#operation/PostingAPI_FbsPostingProductExemplarCreateOrGetV6).<br><br>Если у вас несколько одинаковых товаров в отправлении, укажите один `product_id` и массив `exemplars` для каждого товара из отправления.<br><br>Всегда передавайте полный набор данных по экземплярам и продуктам. <br><br>Например, в вашей системе 10 экземпляров. <br>Вы передали их для проверки и сохранения. <br>Потом добавили в своей системе ещё 60 экземпляров.<br>При повторной передаче экземпляров для проверки и сохранения укажите все экземпляры: и старые, и только что добавленные.<br><br>Код ответа 200 не гарантирует, что данные об экземплярах приняты. <br>Он указывает, что создана задача для добавления информации. <br>Чтобы проверить статус задачи, используйте метод [/v5/fbs/posting/product/exemplar/status](#operation/PostingAPI_FbsPostingProductExemplarStatusV5).<br>
- Tags: `FBS&rFBSMarks`

#### Параметры

| Где | Имя | Обязательный | Тип | Nullable | Описание |
| --- | --- | --- | --- | --- | --- |
| header | `Client-Id` | не указано | unspecified | нет | Исходная ссылка #/components/parameters/Client-Id не разрешается: components.parameters отсутствует в снимке. |
| header | `Api-Key` | не указано | unspecified | нет | Исходная ссылка #/components/parameters/Api-Key не разрешается: components.parameters отсутствует в снимке. |

#### Request body

Обязательный: **да**.
- `application/json`: [`v6FbsPostingProductExemplarSetV6Request`](#schema-v6fbspostingproductexemplarsetv6request)

#### Responses

| Status | Описание | Content / schema |
| --- | --- | --- |
| `200` | Запрос обработан | без тела |
| `default` | Ошибка | `application/json`: [`rpcStatus`](#schema-rpcstatus) |

## Справочник схем

### ExemplarMark

<a id="schema-exemplarmark"></a>

- Тип: `object`
- Nullable: **нет**
- Ограничения: —

#### Поля

| Поле | Required | Тип / вложенная ссылка | Nullable | Ограничения и enum | Description |
| --- | --- | --- | --- | --- | --- |
| `mark` | нет | `string` | нет | — | Значение кода маркировки. |
| `mark_type` | нет | `string` | нет | — | Тип кода маркировки:<br> - `mandatory_mark` — обязательная маркировка «Честный ЗНАК»;<br> - `jw_uin` — уникальный идентификационный номер (УИН) ювелирного изделия;<br> - `imei` — IMEI мобильного устройства.<br> |

### ExemplarsMarks

<a id="schema-exemplarsmarks"></a>

- Тип: `object`
- Nullable: **нет**
- Ограничения: —

#### Поля

| Поле | Required | Тип / вложенная ссылка | Nullable | Ограничения и enum | Description |
| --- | --- | --- | --- | --- | --- |
| `mark` | нет | `string` | нет | — | Значение кода маркировки. |
| `mark_type` | нет | `string` | нет | — | Тип кода маркировки:<br> - `mandatory_mark` — обязательная маркировка «Честный ЗНАК»;<br> - `jw_uin` — уникальный идентификационный номер (УИН) ювелирного изделия;<br> - `imei` — IMEI мобильного устройства.<br> |

### FbsPostingDetailCourier

<a id="schema-fbspostingdetailcourier"></a>

Данные о курьере.

- Тип: `object`
- Nullable: **нет**
- Ограничения: —

#### Поля

| Поле | Required | Тип / вложенная ссылка | Nullable | Ограничения и enum | Description |
| --- | --- | --- | --- | --- | --- |
| `car_model` | нет | `string` | нет | — | Модель автомобиля. |
| `car_number` | нет | `string` | нет | — | Номер автомобиля. |
| `name` | нет | `string` | нет | — | Полное имя курьера. |
| `phone` | нет | `string` | нет | — | Телефон курьера. <br><br>Всегда возвращает пустую строку `""`.<br> |

### FbsPostingDetailPrrOption

<a id="schema-fbspostingdetailprroption"></a>

Информация об услуге погрузочно-разгрузочных работ. Актуально для КГТ-отправлений с доставкой силами продавца или интегрированной службой.

- Тип: `object`
- Nullable: **нет**
- Ограничения: —

#### Поля

| Поле | Required | Тип / вложенная ссылка | Nullable | Ограничения и enum | Description |
| --- | --- | --- | --- | --- | --- |
| `code` | нет | `string` | нет | — | Код услуги погрузочно-разгрузочных работ:<br>- `lift` — подъём на лифте.<br>- `stairs` — подъём по лестнице.<br>- `none` — покупатель отказался от услуги, поднимать товары не нужно.<br>- `delivery_default` — доставка включена в стоимость, по условиям оферты нужно доставить товар на этаж.<br> |
| `price` | нет | `string` | нет | — | Стоимость услуги, которую Ozon компенсирует продавцу. |
| `currency_code` | нет | `string` | нет | — | Валюта. |
| `floor` | нет | `string` | нет | — | Этаж, на который нужно поднять товар. |

### FbsPostingProductExemplarCreateOrGetV6ResponseProduct

<a id="schema-fbspostingproductexemplarcreateorgetv6responseproduct"></a>

- Тип: `object`
- Nullable: **нет**
- Ограничения: —

#### Поля

| Поле | Required | Тип / вложенная ссылка | Nullable | Ограничения и enum | Description |
| --- | --- | --- | --- | --- | --- |
| `exemplars` | нет | array&lt;[`ProductExemplar`](#schema-productexemplar)&gt; | нет | — | Информация об экземплярах. |
| `has_imei` | нет | `boolean` | нет | — | Признак наличия IMEI.<br><br>Если IMEI есть — `true`.<br> |
| `is_gtd_needed` | нет | `boolean` | нет | — | Признак того, что необходимо передать номер грузовой таможенной декларации (ГТД) для продукта и отправления. |
| `is_jw_uin_needed` | нет | `boolean` | нет | — | Признак того, что необходимо передать уникальный идентификационный номер ювелирного изделия (УИН). |
| `is_mandatory_mark_needed` | нет | `boolean` | нет | — | Признак того, что необходимо передать маркировку «Честный ЗНАК». |
| `is_mandatory_mark_possible` | нет | `boolean` | нет | — | Признак того, что возможно заполнить маркировку «Честный ЗНАК». |
| `is_rnpt_needed` | нет | `boolean` | нет | — | Признак того, что необходимо передать номер партии товара (РНПТ). |
| `product_id` | нет | `integer` | нет | format=`"int64"` | Идентификатор товара в системе Ozon — SKU. |
| `quantity` | нет | `integer` | нет | format=`"int32"` | Количество экземпляров. |
| `is_weight_needed` | нет | `boolean` | нет | — | `true`, если товар весовой.<br> |
| `weight_max` | нет | `number` | нет | format=`"float"` | Максимальный вес экземпляра. |
| `weight_min` | нет | `number` | нет | format=`"float"` | Минимальный вес экземпляра. |

### FbsPostingProductExemplarSetV6RequestExemplars

<a id="schema-fbspostingproductexemplarsetv6requestexemplars"></a>

- Тип: `object`
- Nullable: **нет**
- Ограничения: —

#### Поля

| Поле | Required | Тип / вложенная ссылка | Nullable | Ограничения и enum | Description |
| --- | --- | --- | --- | --- | --- |
| `exemplar_id` | да | `integer` | нет | format=`"int64"` | Идентификатор экземпляра. |
| `gtd` | нет | `string` | нет | — | Номер грузовой таможенной декларации (ГТД). |
| `is_gtd_absent` | нет | `boolean` | нет | — | Признак того, что не указан номер грузовой таможенной декларации (ГТД). |
| `is_rnpt_absent` | нет | `boolean` | нет | — | Признак того, что не указан регистрационный номер партии товара (РНПТ). |
| `marks` | нет | array&lt;[`ExemplarsMarks`](#schema-exemplarsmarks)&gt; | нет | — | Список контрольных идентификационных знаков (КИЗ) и других маркировок в одном экземпляре. |
| `rnpt` | нет | `string` | нет | — | Регистрационный номер партии товара (РНПТ). |
| `weight` | нет | `number` | нет | format=`"float"` | Фактический вес экземпляра. |

### FbsPostingProductExemplarSetV6RequestProducts

<a id="schema-fbspostingproductexemplarsetv6requestproducts"></a>

- Тип: `object`
- Nullable: **нет**
- Ограничения: —

#### Поля

| Поле | Required | Тип / вложенная ссылка | Nullable | Ограничения и enum | Description |
| --- | --- | --- | --- | --- | --- |
| `exemplars` | да | array&lt;[`FbsPostingProductExemplarSetV6RequestExemplars`](#schema-fbspostingproductexemplarsetv6requestexemplars)&gt; | нет | — | Информация об экземплярах. |
| `product_id` | да | `integer` | нет | format=`"int64"` | Идентификатор товара в системе Ozon — SKU. |

### FbsPostingShipV4RequestPackage

<a id="schema-fbspostingshipv4requestpackage"></a>

- Тип: `object`
- Nullable: **нет**
- Ограничения: —

#### Поля

| Поле | Required | Тип / вложенная ссылка | Nullable | Ограничения и enum | Description |
| --- | --- | --- | --- | --- | --- |
| `products` | да | array&lt;[`FbsPostingShipV4RequestPackageProduct`](#schema-fbspostingshipv4requestpackageproduct)&gt; | нет | — | Список товаров в отправлении. |

### FbsPostingShipV4RequestPackageProduct

<a id="schema-fbspostingshipv4requestpackageproduct"></a>

- Тип: `object`
- Nullable: **нет**
- Ограничения: —

#### Поля

| Поле | Required | Тип / вложенная ссылка | Nullable | Ограничения и enum | Description |
| --- | --- | --- | --- | --- | --- |
| `product_id` | да | `integer` | нет | format=`"int64"` | Идентификатор товара в системе Ozon — SKU. |
| `quantity` | да | `integer` | нет | format=`"int32"` | Количество экземпляров. |

### FbsPostingShipV4RequestWith

<a id="schema-fbspostingshipv4requestwith"></a>

Дополнительная информация.

- Тип: `object`
- Nullable: **нет**
- Ограничения: —

#### Поля

| Поле | Required | Тип / вложенная ссылка | Nullable | Ограничения и enum | Description |
| --- | --- | --- | --- | --- | --- |
| `additional_data` | нет | `boolean` | нет | — | Чтобы получить дополнительную информацию, передайте `true`. |

### FbsPostingShipV4ResponseShipAdditionalData

<a id="schema-fbspostingshipv4responseshipadditionaldata"></a>

- Тип: unspecified
- Nullable: **нет**
- Ограничения: —

#### Поля

| Поле | Required | Тип / вложенная ссылка | Nullable | Ограничения и enum | Description |
| --- | --- | --- | --- | --- | --- |
| `posting_number` | нет | `string` | нет | — | Номер отправления. |
| `products` | нет | unspecified | нет | — | Список товаров в отправлении. |

### PostingFinancialDataProduct

<a id="schema-postingfinancialdataproduct"></a>

- Тип: `object`
- Nullable: **нет**
- Ограничения: —

#### Поля

| Поле | Required | Тип / вложенная ссылка | Nullable | Ограничения и enum | Description |
| --- | --- | --- | --- | --- | --- |
| `actions` | нет | array&lt;`string`&gt; | нет | — | Список акций. |
| `currency_code` | нет | `string` | нет | — | Валюта ваших цен. Cовпадает с валютой, которая установлена в настройках личного кабинета.<br><br>Возможные значения: <br>  - `RUB` — российский рубль,<br>  - `BYN` — белорусский рубль,<br>  - `KZT` — тенге,<br>  - `EUR` — евро,<br>  - `USD` — доллар США,<br>  - `CNY` — юань.<br> |
| `customer_currency_code` | нет | `string` | нет | — | Код валюты покупателя. |
| `commission_amount` | нет | `number` | нет | format=`"double"` | Размер комиссии за товар. |
| `commission_percent` | нет | `integer` | нет | format=`"int64"` | Процент комиссии. |
| `commissions_currency_code` | нет | `string` | нет | — | Код валюты, в которой рассчитывались комиссии. |
| `old_price` | нет | `number` | нет | format=`"double"` | Цена до учёта скидок. На карточке товара отображается зачёркнутой. |
| `payout` | нет | `number` | нет | format=`"double"` | Выплата продавцу. |
| `price` | нет | `number` | нет | format=`"double"` | Цена товара с учётом акций, кроме акций за счёт Ozon. |
| `customer_price` | нет | `number` | нет | format=`"double"` | Цена товара для покупателя с учётом скидок продавца и Ozon. |
| `product_id` | нет | `integer` | нет | format=`"int64"` | Идентификатор товара в системе Ozon — SKU. |
| `quantity` | нет | `integer` | нет | format=`"int64"` | Количество товара в отправлении. |
| `total_discount_percent` | нет | `number` | нет | format=`"double"` | Процент скидки. |
| `total_discount_value` | нет | `number` | нет | format=`"double"` | Сумма скидки. |

### ProductExemplar

<a id="schema-productexemplar"></a>

- Тип: `object`
- Nullable: **нет**
- Ограничения: —

#### Поля

| Поле | Required | Тип / вложенная ссылка | Nullable | Ограничения и enum | Description |
| --- | --- | --- | --- | --- | --- |
| `exemplar_id` | нет | `integer` | нет | format=`"int64"` | Идентификатор экземпляра. |
| `gtd` | нет | `string` | нет | — | Номер грузовой таможенной декларации (ГТД). |
| `is_gtd_absent` | нет | `boolean` | нет | — | Признак того, что не указан номер грузовой таможенной декларации (ГТД). |
| `is_rnpt_absent` | нет | `boolean` | нет | — | Признак того, что не указан регистрационный номер партии товара (РНПТ). |
| `marks` | нет | array&lt;[`ExemplarMark`](#schema-exemplarmark)&gt; | нет | — | Список контрольных идентификационных знаков (КИЗ) и других маркировок в одном экземпляре. |
| `rnpt` | нет | `string` | нет | — | Регистрационный номер партии товара (РНПТ). |
| `weight` | нет | `number` | нет | format=`"float"` | Фактический вес экземпляра. |

### ResultUnprintedPosting

<a id="schema-resultunprintedposting"></a>

- Тип: `object`
- Nullable: **нет**
- Ограничения: —

#### Поля

| Поле | Required | Тип / вложенная ссылка | Nullable | Ограничения и enum | Description |
| --- | --- | --- | --- | --- | --- |
| `msg` | нет | `string` | нет | — | Причина ошибки. |
| `posting_number` | нет | `string` | нет | — | Номер отправления. |

### SetPostingsResponseResult

<a id="schema-setpostingsresponseresult"></a>

- Тип: `object`
- Nullable: **нет**
- Ограничения: —

#### Поля

| Поле | Required | Тип / вложенная ссылка | Nullable | Ограничения и enum | Description |
| --- | --- | --- | --- | --- | --- |
| `error` | нет | `string` | нет | — | Описание ошибки. |
| `posting_number` | нет | `string` | нет | — | Номер отправления. |
| `result` | нет | `boolean` | нет | — | Результат обработки запроса. `true`, если запрос был обработан успешно.<br> |

### carriageCarriageGetRequest

<a id="schema-carriagecarriagegetrequest"></a>

- Тип: `object`
- Nullable: **нет**
- Ограничения: —

#### Поля

| Поле | Required | Тип / вложенная ссылка | Nullable | Ограничения и enum | Description |
| --- | --- | --- | --- | --- | --- |
| `carriage_id` | да | `integer` | нет | format=`"int64"` | Идентификатор перевозки. |

### carriageCarriageGetResponse

<a id="schema-carriagecarriagegetresponse"></a>

- Тип: `object`
- Nullable: **нет**
- Ограничения: —

#### Поля

| Поле | Required | Тип / вложенная ссылка | Nullable | Ограничения и enum | Description |
| --- | --- | --- | --- | --- | --- |
| `act_type` | нет | `string` | нет | — | Тип акта приёма-передачи. Актуально для продавцов FBS. |
| `all_blr_traceable` | нет | `boolean` | нет | — | `true`, если отгрузка с прослеживаемыми товарами.<br> |
| `is_waybill_enabled` | нет | `boolean` | нет | — | `true`, если доступна печать транспортной накладной.<br> |
| `is_econom` | нет | `boolean` | нет | — | `true`, если отгрузка относится к товарам «Суперэконом».<br> |
| `arrival_pass_ids` | нет | array&lt;`string`&gt; | нет | — | Список идентификаторов пропусков, оформленных на перевозку. |
| `available_actions` | нет | array&lt;`string`&gt; | нет | — | Доступные действия с перевозкой:<br>- `get_shipping_list` — получить лист отгрузки;<br>- `get_act_of_acceptance` — получить акт приёма-передачи;<br>- `get_waybill` — получить товарную накладную в формате PDF;<br>- `set_arrival_passes` — [оформить пропуск](#operation/carriagePassCreate).<br> |
| `cancel_availability` | нет | [`carriageCarriageGetResponseCancelAvailability`](#schema-carriagecarriagegetresponsecancelavailability) | нет | — | — |
| `carriage_id` | нет | `integer` | нет | format=`"int64"` | Идентификатор перевозки. |
| `company_id` | нет | `integer` | нет | format=`"int64"` | Идентификатор продавца. |
| `containers_count` | нет | `integer` | нет | format=`"int32"` | Количество грузовых мест. |
| `created_at` | нет | `string` | нет | format=`"date-time"` | Дата создания перевозки. |
| `delivery_method_id` | нет | `integer` | нет | format=`"int64"` | Идентификатор метода доставки. |
| `departure_date` | нет | `string` | нет | — | Дата выполнения перевозки. |
| `first_mile_type` | нет | `string` | нет | — | Тип первой мили. |
| `has_postings_for_next_carriage` | нет | `boolean` | нет | — | `true`, если есть отправления, которые не попали в перевозку, но нужно отгрузить.<br> |
| `integration_type` | нет | `string` | нет | — | Тип перевозки. |
| `is_container_label_printed` | нет | `boolean` | нет | — | `true`, если вы уже напечатали этикетки на грузовые места.<br> |
| `is_partial` | нет | `boolean` | нет | — | `true`, если перевозка частичная.<br> |
| `partial_num` | нет | `integer` | нет | format=`"int64"` | Порядковый номер частичной перевозки. |
| `retry_count` | нет | `integer` | нет | format=`"int32"` | Количество повторных попыток создания перевозки. |
| `status` | нет | `string` | нет | — | Статус перевозки:<br>- `received` — идёт приёмка,<br>- `closed` — завершена после приёмки,<br>- `sended` — отправлена,<br>- `cancelled` — отменена.<br> |
| `tpl_provider_id` | нет | `integer` | нет | format=`"int64"` | Идентификатор провайдера доставки. |
| `updated_at` | нет | `string` | нет | format=`"date-time"` | Дата последнего обновления информации о перевозке. |
| `warehouse_id` | нет | `integer` | нет | format=`"int64"` | Идентификатор склада. |

### carriageCarriageGetResponseCancelAvailability

<a id="schema-carriagecarriagegetresponsecancelavailability"></a>

Возможность отмены.

- Тип: `object`
- Nullable: **нет**
- Ограничения: —

#### Поля

| Поле | Required | Тип / вложенная ссылка | Nullable | Ограничения и enum | Description |
| --- | --- | --- | --- | --- | --- |
| `is_cancel_available` | нет | `boolean` | нет | — | `true`, если перевозку можно отменить.<br> |
| `reason` | нет | `string` | нет | — | Причина, почему перевозку нельзя отменить. |

### fbsv4FbsPostingShipV4Request

<a id="schema-fbsv4fbspostingshipv4request"></a>

- Тип: `object`
- Nullable: **нет**
- Ограничения: —

#### Поля

| Поле | Required | Тип / вложенная ссылка | Nullable | Ограничения и enum | Description |
| --- | --- | --- | --- | --- | --- |
| `packages` | да | unspecified | нет | — | Список упаковок. Каждая упаковка содержит список отправлений, на которые делится заказ. |
| `posting_number` | да | `string` | нет | — | Номер отправления. |
| `with` | нет | [`FbsPostingShipV4RequestWith`](#schema-fbspostingshipv4requestwith) | нет | — | — |

### fbsv4FbsPostingShipV4Response

<a id="schema-fbsv4fbspostingshipv4response"></a>

- Тип: `object`
- Nullable: **нет**
- Ограничения: —

#### Поля

| Поле | Required | Тип / вложенная ссылка | Nullable | Ограничения и enum | Description |
| --- | --- | --- | --- | --- | --- |
| `additional_data` | нет | unspecified | нет | — | Дополнительная информация об отправлениях. |
| `result` | нет | unspecified | нет | — | Результат сборки отправлений. |

### fbsv4PostingProductDetailWithoutDimensions

<a id="schema-fbsv4postingproductdetailwithoutdimensions"></a>

- Тип: `object`
- Nullable: **нет**
- Ограничения: —

#### Поля

| Поле | Required | Тип / вложенная ссылка | Nullable | Ограничения и enum | Description |
| --- | --- | --- | --- | --- | --- |
| `mandatory_mark` | нет | unspecified | нет | — | Обязательная маркировка «Честный ЗНАК». |
| `name` | нет | `string` | нет | — | Название товара. |
| `offer_id` | нет | `string` | нет | — | Идентификатор товара в системе продавца — артикул. |
| `price` | нет | `string` | нет | — | Цена. |
| `quantity` | нет | `integer` | нет | format=`"int32"` | Количество товара в отправлении. |
| `sku` | нет | `integer` | нет | format=`"int64"` | Идентификатор товара в системе Ozon — SKU. |
| `currency_code` | нет | `string` | нет | — | Валюта ваших цен. Cовпадает с валютой, которая установлена в настройках личного кабинета.<br><br>Возможные значения: <br>  - `RUB` — российский рубль,<br>  - `BYN` — белорусский рубль,<br>  - `KZT` — тенге,<br>  - `EUR` — евро,<br>  - `USD` — доллар США,<br>  - `CNY` — юань.<br> |

### googlerpcStatus

<a id="schema-googlerpcstatus"></a>

- Тип: `object`
- Nullable: **нет**
- Ограничения: —

#### Поля

| Поле | Required | Тип / вложенная ссылка | Nullable | Ограничения и enum | Description |
| --- | --- | --- | --- | --- | --- |
| `code` | нет | `integer` | нет | format=`"int32"` | Код ошибки. |
| `details` | нет | array&lt;[`protobufAny`](#schema-protobufany)&gt; | нет | — | Дополнительная информация об ошибке. |
| `message` | нет | `string` | нет | — | Описание ошибки. |

### money.Money.Current_tariff_charge

<a id="schema-money-money-current-tariff-charge"></a>

Скидка или надбавка.

- Тип: `object`
- Nullable: **нет**
- Ограничения: —

#### Поля

| Поле | Required | Тип / вложенная ссылка | Nullable | Ограничения и enum | Description |
| --- | --- | --- | --- | --- | --- |
| `amount` | нет | `string` | нет | — | Сумма. |
| `currency` | нет | `string` | нет | — | Валюта. |

### money.Money.Current_tariff_min_charge

<a id="schema-money-money-current-tariff-min-charge"></a>

Минимальная скидка или надбавка.

- Тип: `object`
- Nullable: **нет**
- Ограничения: —

#### Поля

| Поле | Required | Тип / вложенная ссылка | Nullable | Ограничения и enum | Description |
| --- | --- | --- | --- | --- | --- |
| `amount` | нет | `string` | нет | — | Сумма. |
| `currency` | нет | `string` | нет | — | Валюта. |

### money.Money.Next_tariff_charge

<a id="schema-money-money-next-tariff-charge"></a>

Скидка или надбавка через время из параметра `next_tariff_starts_at`.

- Тип: `object`
- Nullable: **нет**
- Ограничения: —

#### Поля

| Поле | Required | Тип / вложенная ссылка | Nullable | Ограничения и enum | Description |
| --- | --- | --- | --- | --- | --- |
| `amount` | нет | `string` | нет | — | Сумма. |
| `currency` | нет | `string` | нет | — | Валюта. |

### money.Money.Next_tariff_min_charge

<a id="schema-money-money-next-tariff-min-charge"></a>

Минимальная скидка или надбавка через время из параметра `next_tariff_starts_at`.

- Тип: `object`
- Nullable: **нет**
- Ограничения: —

#### Поля

| Поле | Required | Тип / вложенная ссылка | Nullable | Ограничения и enum | Description |
| --- | --- | --- | --- | --- | --- |
| `amount` | нет | `string` | нет | — | Сумма. |
| `currency` | нет | `string` | нет | — | Валюта. |

### money.postingMoney

<a id="schema-money-postingmoney"></a>

Цена товара.

- Тип: `object`
- Nullable: **нет**
- Ограничения: —

#### Поля

| Поле | Required | Тип / вложенная ссылка | Nullable | Ограничения и enum | Description |
| --- | --- | --- | --- | --- | --- |
| `amount` | нет | `string` | нет | — | Сумма. |
| `currency` | нет | `string` | нет | — | Валюта. |

### posting.v3.FbsPosting.Container.CargoType.Enum

<a id="schema-posting-v3-fbsposting-container-cargotype-enum"></a>

Тип грузоместа: <br>  - `BOX` — коробка;<br>  - `PALLET` — палета.<br>

- Тип: `string`
- Nullable: **нет**
- Ограничения: default=`"BOX"`; enum=`"BOX"`, `"PALLET"`

#### Поля

| Поле | Required | Тип / вложенная ссылка | Nullable | Ограничения и enum | Description |
| --- | --- | --- | --- | --- | --- |
| — | — | — | — | — | — |

### posting.v3.FbsPostingDetail.ExternalOrder

<a id="schema-posting-v3-fbspostingdetail-externalorder"></a>

Информация о заказе с внешней платформы.

- Тип: `object`
- Nullable: **нет**
- Ограничения: —

#### Поля

| Поле | Required | Тип / вложенная ссылка | Nullable | Ограничения и enum | Description |
| --- | --- | --- | --- | --- | --- |
| `is_external` | нет | `boolean` | нет | — | `true`, если заказ с внешней платформы.<br> |
| `platform_name` | нет | `string` | нет | — | Название платформы, с которой сделали заказ. |

### posting.v3.FbsPostingDetail.SortingCenter

<a id="schema-posting-v3-fbspostingdetail-sortingcenter"></a>

Информация о сортировочном центре, в который нужно привезти отправление. Для `integration_type_flow = hybrid_3pl_tracking`.<br>Если значение `null`, информацию получить не удалось.<br>

- Тип: `object`
- Nullable: **нет**
- Ограничения: —

#### Поля

| Поле | Required | Тип / вложенная ссылка | Nullable | Ограничения и enum | Description |
| --- | --- | --- | --- | --- | --- |
| `code` | нет | `string` | нет | — | Код сортировочного центра. |
| `name` | нет | `string` | нет | — | Название сортировочного центра. |

### posting.v4.PostingFbsListRequest

<a id="schema-posting-v4-postingfbslistrequest"></a>

- Тип: `object`
- Nullable: **нет**
- Ограничения: —

#### Поля

| Поле | Required | Тип / вложенная ссылка | Nullable | Ограничения и enum | Description |
| --- | --- | --- | --- | --- | --- |
| `cursor` | нет | `string` | нет | — | Указатель для выборки следующих данных. |
| `filter` | да | [`posting.v4.PostingFbsListRequest.Filter`](#schema-posting-v4-postingfbslistrequest-filter) | нет | — | — |
| `limit` | да | `integer` | нет | format=`"int64"`; minimum=`1`; maximum=`100` | Количество значений в ответе. |
| `sort_dir` | нет | [`posting.v4.PostingFbsListRequest.SortDir.Enum`](#schema-posting-v4-postingfbslistrequest-sortdir-enum) | нет | — | — |
| `translit` | нет | `boolean` | нет | — | `true`, чтобы включить транслитерацию адреса из кириллицы в латиницу.<br> |
| `with` | нет | [`posting.v4.PostingFbsListRequest.With`](#schema-posting-v4-postingfbslistrequest-with) | нет | — | — |

### posting.v4.PostingFbsListRequest.Filter

<a id="schema-posting-v4-postingfbslistrequest-filter"></a>

Фильтр.

- Тип: `object`
- Nullable: **нет**
- Ограничения: —

#### Поля

| Поле | Required | Тип / вложенная ссылка | Nullable | Ограничения и enum | Description |
| --- | --- | --- | --- | --- | --- |
| `delivery_method_ids` | нет | array&lt;`string`&gt; | нет | maxItems=`1000` | Идентификатор способа доставки. Можно получить с помощью метода [/v1/delivery-method/list](#operation/WarehouseAPI_DeliveryMethodList).<br> |
| `integration_type_flow` | нет | array&lt;`string`&gt; | нет | — | Процесс обработки отправления:<br>- `ozon` — доставка силами Ozon;<br>- `aggregator` — доставка внешней службой, Ozon регистрирует заказ;<br>- `non_integrated` — доставка силами продавца;<br>- `3pl_tracking` — доставка внешней службой, продавец регистрирует заказ;<br>- `hybrid` — гибридная интеграция;<br>- `hybrid_aggregator` — гибридная интеграция с доставкой внешней службой, Ozon регистрирует заказ;<br>- `hybrid_non_integrated` — гибридная интеграция с доставкой силами продавца;<br>- `hybrid_3pl_tracking` — гибридная интеграция с доставкой внешней службой, продавец регистрирует заказ;<br>- `click_and_collect` — бронирование в магазине партнёра;<br>- `FBP` — доставка с партнёрских складов Ozon.<br> |
| `is_blr_traceable` | нет | `boolean` | нет | — | `true`, если товар отслеживаемый.<br> |
| `last_changed_status_date` | нет | [`posting.v4.PostingFbsListRequest.Filter.LastChangedStatusDate`](#schema-posting-v4-postingfbslistrequest-filter-lastchangedstatusdate) | нет | — | — |
| `order_id` | нет | `integer` | нет | format=`"int64"` | Идентификатор заказа. |
| `order_numbers` | нет | array&lt;`string`&gt; | нет | maxItems=`100` | Номера заказов, к которым относятся отправления. |
| `provider_ids` | нет | array&lt;`string`&gt; | нет | maxItems=`1000` | Идентификатор службы доставки. Можно получить с помощью метода [/v1/delivery-method/list](#operation/WarehouseAPI_DeliveryMethodList).<br> |
| `since` | да | `string` | нет | format=`"date-time"`; pattern=`" YYYY-MM-DDThh:mm:ssZ"` | Дата начала периода, за который нужно получить список отправлений. |
| `statuses` | нет | array&lt;`string`&gt; | нет | — | Статус отправления:<br>- `awaiting_registration` — ожидает регистрации;<br>- `acceptance_in_progress` — идёт приёмка;<br>- `awaiting_approve` — ожидает подтверждения;<br>- `awaiting_packaging` — ожидает упаковки;<br>- `awaiting_deliver` — ожидает отгрузки;<br>- `arbitration` — арбитраж;<br>- `client_arbitration` — клиентский арбитраж доставки;<br>- `delivering` — доставляется;<br>- `driver_pickup` — у водителя;<br>- `delivered` — доставлено;<br>- `cancelled` — отменено;<br>- `not_accepted` — не принято на сортировочном центре;<br>- `sent_by_seller` – отправлено продавцом.<br> |
| `to` | да | `string` | нет | format=`"date-time"`; pattern=`" YYYY-MM-DDThh:mm:ssZ"` | Дата конца периода, за который нужно получить список отправлений. |
| `warehouse_ids` | нет | array&lt;`string`&gt; | нет | maxItems=`1000` | Идентификатор склада. Можно получить с помощью метода [/v1/warehouse/list](#operation/WarehouseAPI_WarehouseList). |

### posting.v4.PostingFbsListRequest.Filter.LastChangedStatusDate

<a id="schema-posting-v4-postingfbslistrequest-filter-lastchangedstatusdate"></a>

Период, в который последний раз изменялся статус у отправлений.

- Тип: `object`
- Nullable: **нет**
- Ограничения: —

#### Поля

| Поле | Required | Тип / вложенная ссылка | Nullable | Ограничения и enum | Description |
| --- | --- | --- | --- | --- | --- |
| `from` | нет | `string` | нет | format=`"date-time"` | Дата начала периода. |
| `to` | нет | `string` | нет | format=`"date-time"` | Дата окончания периода. |

### posting.v4.PostingFbsListRequest.SortDir.Enum

<a id="schema-posting-v4-postingfbslistrequest-sortdir-enum"></a>

Направление сортировки:<br>- `ASC` — по возрастанию;<br>- `DESC` — по убыванию.<br>

- Тип: `string`
- Nullable: **нет**
- Ограничения: enum=`"ASC"`, `"DESC"`

#### Поля

| Поле | Required | Тип / вложенная ссылка | Nullable | Ограничения и enum | Description |
| --- | --- | --- | --- | --- | --- |
| — | — | — | — | — | — |

### posting.v4.PostingFbsListRequest.With

<a id="schema-posting-v4-postingfbslistrequest-with"></a>

Дополнительные поля, которые нужно добавить в ответ.

- Тип: `object`
- Nullable: **нет**
- Ограничения: —

#### Поля

| Поле | Required | Тип / вложенная ссылка | Nullable | Ограничения и enum | Description |
| --- | --- | --- | --- | --- | --- |
| `analytics_data` | нет | `boolean` | нет | — | `true`, чтобы добавить в ответ данные аналитики.<br> |
| `barcodes` | нет | `boolean` | нет | — | `true`, чтобы добавить в ответ штрихкоды отправления.<br> |
| `financial_data` | нет | `boolean` | нет | — | `true`, чтобы добавить в ответ финансовые данные.<br> |
| `legal_info` | нет | `boolean` | нет | — | `true`, чтобы добавить в ответ юридическую информацию.<br> |

### posting.v4.PostingFbsListResponse

<a id="schema-posting-v4-postingfbslistresponse"></a>

- Тип: `object`
- Nullable: **нет**
- Ограничения: —

#### Поля

| Поле | Required | Тип / вложенная ссылка | Nullable | Ограничения и enum | Description |
| --- | --- | --- | --- | --- | --- |
| `cursor` | нет | `string` | нет | — | Указатель для выборки следующих данных. |
| `has_next` | нет | `boolean` | нет | — | `true`, если в ответе вернулись не все отправления.<br> |
| `postings` | нет | unspecified | нет | — | Список отправлений. |

### posting.v4.PostingFbsListResponse.Postings

<a id="schema-posting-v4-postingfbslistresponse-postings"></a>

- Тип: `object`
- Nullable: **нет**
- Ограничения: —

#### Поля

| Поле | Required | Тип / вложенная ссылка | Nullable | Ограничения и enum | Description |
| --- | --- | --- | --- | --- | --- |
| `addressee` | нет | [`posting.v4.PostingFbsListResponse.Postings.Addressee`](#schema-posting-v4-postingfbslistresponse-postings-addressee) | нет | — | — |
| `analytics_data` | нет | [`posting.v4.PostingFbsListResponse.Postings.AnalyticsData`](#schema-posting-v4-postingfbslistresponse-postings-analyticsdata) | нет | — | — |
| `available_actions` | нет | array&lt;`string`&gt; | нет | — | Доступные действия и информация об отправлении:<br>- `arbitration` — открыть спор;<br>- `awaiting_delivery` — перевести в статус «Ожидает отгрузки»;<br>- `can_create_chat` — начать чат с покупателем;<br>- `cancel` — отменить отправление;<br>- `click_track_number` — просмотреть по трек-номеру историю изменения статусов в личном кабинете;<br>- `customer_phone_available` — телефон покупателя;<br>- `has_weight_products` — весовые товары в отправлении;<br>- `hide_region_and_city` — скрыть регион и город покупателя в отчёте;<br>- `invoice_get` —  получить информацию из счёта-фактуры;<br>- `invoice_send` — создать счёт-фактуру;<br>- `invoice_update` — отредактировать счёт-фактуру;<br>- `label_download_big` — скачать большую этикетку;<br>- `label_download_small` — скачать маленькую этикетку;<br>- `label_download` — скачать этикетку;<br>- `non_int_delivered` — перевести в статус «Условно доставлен»;<br>- `non_int_delivering` — перевести в статус «Доставляется»;<br>- `non_int_last_mile` — перевести в статус «Курьер в пути»;<br>- `product_cancel` — отменить часть товаров в отправлении;<br>- `set_cutoff` — укажите дату отгрузки методом [/v1/posting/cutoff/set](#operation/PostingAPI_SetPostingCutoff) не позже даты в параметре `shipment_date`;<br>- `set_timeslot` — изменить время доставки покупателю;<br>- `set_track_number` — указать или изменить трек-номер;<br>- `ship_async_in_process` — отправление собирается;<br>- `ship_async_retry` — собрать отправление повторно после ошибки сборки;<br>- `ship_async` — собрать отправление;<br>- `ship_with_additional_info` — заполните дополнительную информацию методом [/v6/fbs/posting/product/exemplar/set](https://docs.ozon.ru/api/seller/#operation/PostingAPI_FbsPostingProductExemplarSetV6);<br>- `ship` — собрать отправление;<br>- `update_cis` — изменить дополнительную информацию.<br> |
| `barcodes` | нет | [`posting.v4.PostingFbsListResponse.Postings.Barcodes`](#schema-posting-v4-postingfbslistresponse-postings-barcodes) | нет | — | — |
| `cancellation` | нет | [`posting.v4.PostingFbsListResponse.Postings.Cancellation`](#schema-posting-v4-postingfbslistresponse-postings-cancellation) | нет | — | — |
| `customer` | нет | [`posting.v4.PostingFbsListResponse.Postings.Customer`](#schema-posting-v4-postingfbslistresponse-postings-customer) | нет | — | — |
| `container` | нет | [`posting.v4.PostingFbsListResponse.Postings.Container`](#schema-posting-v4-postingfbslistresponse-postings-container) | нет | — | — |
| `container_sort_type` | нет | `string` | нет | — | Тип сортировки грузоместа:<br>  - `SORT` — сортируемый;<br>  - `NON-SORT` — несортируемый.<br> |
| `delivering_date` | нет | `string` | нет | format=`"date-time"` | Дата передачи отправления в доставку. |
| `delivery_method` | нет | [`posting.v4.PostingFbsListResponse.Postings.DeliveryMethod`](#schema-posting-v4-postingfbslistresponse-postings-deliverymethod) | нет | — | — |
| `delivery_schema` | нет | `string` | нет | — | Схема доставки:<br>- `SDS` — идентификатор единого SKU;<br>- `FBO` — идентификатор товара, который продаётся со склада Ozon;<br>- `FBS` — идентификатор товара, который продаётся со склада FBS;<br>- `Crossborder` — идентификатор товара, который продаётся из-за границы.<br> |
| `destination_place_id` | нет | `integer` | нет | format=`"int64"` | Идентификатор места назначения. |
| `destination_place_name` | нет | `string` | нет | — | Название места назначения. |
| `external_order` | нет | [`posting.v4.PostingFbsListResponse.Postings.ExternalOrder`](#schema-posting-v4-postingfbslistresponse-postings-externalorder) | нет | — | — |
| `financial_data` | нет | [`posting.v4.PostingFbsListResponse.Postings.FinancialData`](#schema-posting-v4-postingfbslistresponse-postings-financialdata) | нет | — | — |
| `in_process_at` | нет | `string` | нет | format=`"date-time"` | Дата и время начала обработки отправления. |
| `is_click_and_collect` | нет | `boolean` | нет | — | `true`, если отправление доставляется методом «Самовывоз из магазина».<br> |
| `is_express` | нет | `boolean` | нет | — | `true`, если использовалась быстрая доставка Ozon Express.<br> |
| `is_multibox` | нет | `boolean` | нет | — | Признак, что в отправлении есть многокоробочный товар и нужно передать количество коробок для него:<br><br>- `true` — до сборки передайте количество коробок через метод [/v3/posting/multiboxqty/set](#operation/PostingAPI_PostingMultiBoxQtySetV3).<br>- `false` — отправление собрано с указанием количества коробок в параметре `multi_box_qty` или в отправлении нет многокоробочного товара.<br> |
| `is_presortable` | нет | `boolean` | нет | — | `true`, если товар — пересорт.<br> |
| `integration_type_flow` | нет | `string` | нет | — | Процесс обработки отправления:<br>- `ozon` — доставка силами Ozon;<br>- `aggregator` — доставка внешней службой, Ozon регистрирует заказ;<br>- `non_integrated` — доставка силами продавца;<br>- `3pl_tracking` — доставка внешней службой, продавец регистрирует заказ;<br>- `hybrid` — гибридная интеграция;<br>- `hybrid_aggregator` — гибридная интеграция с доставкой внешней службой, Ozon регистрирует заказ;<br>- `hybrid_non_integrated` — гибридная интеграция с доставкой силами продавца;<br>- `hybrid_3pl_tracking` — гибридная интеграция с доставкой внешней службой, продавец регистрирует заказ;<br>- `click_and_collect` — бронирование в магазине партнёра;<br>- `FBP` — доставка с партнёрских складов Ozon.<br> |
| `legal_info` | нет | [`posting.v4.PostingFbsListResponse.Postings.LegalInfo`](#schema-posting-v4-postingfbslistresponse-postings-legalinfo) | нет | — | — |
| `multi_box_qty` | нет | `integer` | нет | format=`"int32"` | Количество коробок, в которые упакован товар. |
| `optional` | нет | [`posting.v4.PostingFbsListResponse.Postings.Optional`](#schema-posting-v4-postingfbslistresponse-postings-optional) | нет | — | — |
| `order_id` | нет | `integer` | нет | format=`"int64"` | Идентификатор заказа, к которому относится отправление. |
| `order_number` | нет | `string` | нет | — | Номер заказа, к которому относится отправление. |
| `parent_posting_number` | нет | `string` | нет | — | Номер родительского отправления, в результате разделения которого появилось текущее. |
| `pickup_code_verified_at` | нет | `string` | нет | format=`"date-time"` | Дата и время успешной валидации кода курьера. Проверьте код курьера методом [/v1/posting/fbs/pick-up-code/verify](#operation/PostingAPI_PostingFBSPickupCodeVerify). |
| `posting_number` | нет | `string` | нет | — | Номер отправления. |
| `products` | нет | array&lt;[`posting.v4.PostingFbsListResponse.Postings.Products`](#schema-posting-v4-postingfbslistresponse-postings-products)&gt; | нет | — | Список товаров в отправлении. |
| `prr_option` | нет | `string` | нет | — | Код услуги погрузочно-разгрузочных работ:<br>- `lift` — подъём на лифте;<br>- `stairs` — подъём по лестнице;<br>- `none` — покупатель отказался от услуги, поднимать товары не нужно;<br>- `delivery_default` — доставка включена в стоимость, по условиям оферты нужно доставить товар на этаж.<br><br>Для КГТ-отправлений с доставкой силами продавца или интегрированной службой.<br> |
| `quantum_id` | нет | `integer` | нет | format=`"int64"` | Идентификатор эконом-товара. |
| `require_blr_traceable_attrs` | нет | `boolean` | нет | — | `true`, если нужно заполнить атрибуты отслеживаемости.<br> |
| `requirements` | нет | [`posting.v4.PostingFbsListResponse.Postings.Requirements`](#schema-posting-v4-postingfbslistresponse-postings-requirements) | нет | — | — |
| `shipment_date` | нет | `string` | нет | format=`"date-time"` | Дата и время, до которой нужно собрать отправление. Показываем рекомендованное время отгрузки. По истечении этого времени начнёт применяться новый тариф, информацию о нём получите в поле `tariffication`. |
| `shipment_date_without_delay` | нет | `string` | нет | format=`"date-time"` | Дата и время отгрузки без просрочки. |
| `sorting_center` | нет | [`posting.v4.PostingFbsListResponse.Postings.SortingCenter`](#schema-posting-v4-postingfbslistresponse-postings-sortingcenter) | нет | — | — |
| `status` | нет | `string` | нет | — | Статус отправления:<br>- `acceptance_in_progress` — идёт приёмка;<br>- `arbitration` — арбитраж;<br>- `awaiting_approve` — ожидает подтверждения;<br>- `awaiting_deliver` — ожидает отгрузки;<br>- `awaiting_packaging` — ожидает упаковки;<br>- `awaiting_registration` — ожидает регистрации;<br>- `awaiting_verification` — создано;<br>- `cancelled` — отменено;<br>- `cancelled_from_split_pending` — отменено из-за разделения отправления;<br>- `client_arbitration` — клиентский арбитраж доставки;<br>- `delivering` — доставляется;<br>- `driver_pickup` — у водителя;<br>- `not_accepted` — не принято на сортировочном центре.<br> |
| `substatus` | нет | `string` | нет | — | Подстатус отправления:<br>- `posting_acceptance_in_progress`— идёт приёмка;<br>- `posting_in_arbitration` — арбитраж;<br>- `posting_created` — создано;<br>- `posting_in_carriage` — в перевозке;<br>- `posting_not_in_carriage` — не добавлено в перевозку;<br>- `posting_registered` — зарегистрировано;<br>- `posting_transferring_to_delivery`, если `status=awaiting_deliver` — передаётся в доставку;<br>- `posting_awaiting_passport_data` — ожидает паспортных данных;<br>- `posting_created` — создано;<br>- `posting_awaiting_registration` — ожидает регистрации;<br>- `posting_registration_error` — ошибка регистрации;<br>- `posting_transferring_to_delivery`, если `status=awaiting_registration` — передаётся курьеру;<br>- `posting_split_pending` — создано;<br>- `posting_canceled` — отменено;<br>- `posting_in_client_arbitration` — клиентский арбитраж доставки;<br>- `posting_delivered` — доставлено;<br>- `posting_received` — получено;<br>- `posting_conditionally_delivered` — условно доставлено;<br>- `posting_in_courier_service` — курьер в пути;<br>- `posting_in_pickup_point` — в пункте выдачи;<br>- `posting_on_way_to_city` — в пути в ваш город;<br>- `posting_on_way_to_pickup_point` — в пути в пункт выдачи;<br>- `posting_returned_to_warehouse` — возвращено на склад;<br>- `posting_transferred_to_courier_service` — передаётся в службу доставки;<br>- `posting_driver_pick_up` — у водителя;<br>- `posting_not_in_sort_center` — не принято на сортировочном центре;<br>- `ship_failed` — сборка не удалась.<br> |
| `tariffication` | нет | [`posting.v4.PostingFbsListResponse.Postings.Tariffication`](#schema-posting-v4-postingfbslistresponse-postings-tariffication) | нет | — | — |
| `tariffication_steps` | нет | array&lt;[`posting.v4.PostingFbsListResponse.Postings.TarifficationStep`](#schema-posting-v4-postingfbslistresponse-postings-tarifficationstep)&gt; | нет | — | Этапы тарификации. |
| `tpl_integration_type` | нет | `string` | нет | — | Тип интеграции со службой доставки:<br>  - `ozon` — доставка службой Ozon;<br>  - `3pl_tracking` — доставка интегрированной службой;<br>  - `non_integrated` — доставка сторонней службой;<br>  - `aggregator` — доставка через партнёрскую доставку Ozon;<br>  - `hybryd` — схема доставки Почты России.<br> |
| `tracking_number` | нет | `string` | нет | — | Трек-номер отправления. |
| `volume_weight` | нет | `number` | нет | format=`"double"` | Объёмный вес товара. |

### posting.v4.PostingFbsListResponse.Postings.Addressee

<a id="schema-posting-v4-postingfbslistresponse-postings-addressee"></a>

Контактные данные получателя.

- Тип: `object`
- Nullable: **нет**
- Ограничения: —

#### Поля

| Поле | Required | Тип / вложенная ссылка | Nullable | Ограничения и enum | Description |
| --- | --- | --- | --- | --- | --- |
| `name` | нет | `string` | нет | — | Имя получателя. |

### posting.v4.PostingFbsListResponse.Postings.AnalyticsData

<a id="schema-posting-v4-postingfbslistresponse-postings-analyticsdata"></a>

Данные аналитики.

- Тип: `object`
- Nullable: **нет**
- Ограничения: —

#### Поля

| Поле | Required | Тип / вложенная ссылка | Nullable | Ограничения и enum | Description |
| --- | --- | --- | --- | --- | --- |
| `city` | нет | `string` | нет | — | Город доставки. Только для отправлений rFBS и продавцов из СНГ. |
| `client_delivery_date_begin` | нет | `string` | нет | format=`"date-time"` | Дата и время начала доставки. Только для отправлений, оформленных через [Ozon Доставку](#tag/OzonLogistics). |
| `client_delivery_date_end` | нет | `string` | нет | format=`"date-time"` | Ожидаемая дата, до которой заказ будет доставлен. Только для отправлений, оформленных через [Ozon Доставку](#tag/OzonLogistics). |
| `delivery_date_begin` | нет | `string` | нет | format=`"date-time"` | Дата и время начала доставки. |
| `delivery_date_end` | нет | `string` | нет | format=`"date-time"` | Дата и время конца доставки. |
| `delivery_type` | нет | `string` | нет | — | Способ доставки. |
| `is_legal` | нет | `boolean` | нет | — | `true`, если получатель юридическое лицо.<br> |
| `is_premium` | нет | `boolean` | нет | — | `true`, если у получателя есть подписка Premium.<br> |
| `payment_type_group_name` | нет | `string` | нет | — | Способ оплаты: <br>- `картой онлайн`;<br>- `карта Ozon Банка`;<br>- `автосписание с карты Ozon Банка при выдаче`;<br>- `сохранённой картой при получении`;<br>- `Система Быстрых Платежей`;<br>- `Ozon Рассрочка`;<br>- `оплата на расчётный счёт`;<br>- `SberPay`;<br>- `предоплата на стороне внешнего продавца`.<br> |
| `region` | нет | `string` | нет | — | Регион доставки. Только для отправлений rFBS. |
| `tpl_provider` | нет | `string` | нет | — | Служба доставки. |
| `tpl_provider_id` | нет | `integer` | нет | format=`"int64"` | Идентификатор службы доставки. |
| `warehouse` | нет | `string` | нет | — | Название склада отправки заказа. |
| `warehouse_id` | нет | `integer` | нет | format=`"int64"` | Идентификатор склада. |

### posting.v4.PostingFbsListResponse.Postings.Barcodes

<a id="schema-posting-v4-postingfbslistresponse-postings-barcodes"></a>

Штрихкоды отправления.

- Тип: `object`
- Nullable: **нет**
- Ограничения: —

#### Поля

| Поле | Required | Тип / вложенная ссылка | Nullable | Ограничения и enum | Description |
| --- | --- | --- | --- | --- | --- |
| `lower_barcode` | нет | `string` | нет | — | Нижний штрихкод на маркировке отправления. |
| `upper_barcode` | нет | `string` | нет | — | Верхний штрихкод на маркировке отправления. |

### posting.v4.PostingFbsListResponse.Postings.Cancellation

<a id="schema-posting-v4-postingfbslistresponse-postings-cancellation"></a>

Информация об отмене.

- Тип: `object`
- Nullable: **нет**
- Ограничения: —

#### Поля

| Поле | Required | Тип / вложенная ссылка | Nullable | Ограничения и enum | Description |
| --- | --- | --- | --- | --- | --- |
| `affect_cancellation_rating` | нет | `boolean` | нет | — | `true`, если отмена влияет на рейтинг продавца.<br> |
| `cancel_reason` | нет | `string` | нет | — | Причина отмены. |
| `cancel_reason_id` | нет | `integer` | нет | format=`"int64"` | Идентификатор причины отмены отправления. |
| `cancellation_initiator` | нет | `string` | нет | — | Инициатор отмены:<br>- `Продавец`,<br>- `Клиент`,<br>- `Покупатель`,<br>- `Ozon`,<br>- `Система`,<br>- `Служба доставки`.<br> |
| `cancellation_type` | нет | `string` | нет | — | Тип отмены:<br>- `seller` — отменено продавцом;<br>- `client` или `customer` — отменено покупателем;<br>- `ozon` — отменено Ozon;<br>- `system` — отменено системой;<br>- `delivery` — отменено службой доставки.<br> |
| `cancelled_after_ship` | нет | `boolean` | нет | — | `true`, если отмена произошла после сборки отправления.<br> |

### posting.v4.PostingFbsListResponse.Postings.Container

<a id="schema-posting-v4-postingfbslistresponse-postings-container"></a>

Информация о грузоместе.

- Тип: `object`
- Nullable: **нет**
- Ограничения: —

#### Поля

| Поле | Required | Тип / вложенная ссылка | Nullable | Ограничения и enum | Description |
| --- | --- | --- | --- | --- | --- |
| `cargo_type` | нет | [`posting.v3.FbsPosting.Container.CargoType.Enum`](#schema-posting-v3-fbsposting-container-cargotype-enum) | нет | — | Тип грузоместа. |
| `container_date` | нет | `string` | нет | — | Дата создания грузоместа в часовом поясе склада. |
| `container_id` | нет | `integer` | нет | format=`"int64"` | Идентификатор грузоместа. |
| `container_number` | нет | `integer` | нет | format=`"int32"` | Порядковый номер грузоместа. |

### posting.v4.PostingFbsListResponse.Postings.Customer

<a id="schema-posting-v4-postingfbslistresponse-postings-customer"></a>

Информация о покупателе.

- Тип: `object`
- Nullable: **нет**
- Ограничения: —

#### Поля

| Поле | Required | Тип / вложенная ссылка | Nullable | Ограничения и enum | Description |
| --- | --- | --- | --- | --- | --- |
| `address` | нет | [`posting.v4.PostingFbsListResponse.Postings.Customer.Address`](#schema-posting-v4-postingfbslistresponse-postings-customer-address) | нет | — | — |
| `customer_email` | нет | `string` | нет | — | Электронная почта покупателя. |
| `customer_id` | нет | `integer` | нет | format=`"int64"` | Идентификатор покупателя. |
| `name` | нет | `string` | нет | — | Имя покупателя. |
| `phone` | нет | `string` | нет | — | Подменный контактный телефон покупателя. |

### posting.v4.PostingFbsListResponse.Postings.Customer.Address

<a id="schema-posting-v4-postingfbslistresponse-postings-customer-address"></a>

Адрес доставки.

- Тип: `object`
- Nullable: **нет**
- Ограничения: —

#### Поля

| Поле | Required | Тип / вложенная ссылка | Nullable | Ограничения и enum | Description |
| --- | --- | --- | --- | --- | --- |
| `address_tail` | нет | `string` | нет | — | Адрес в текстовом формате. |
| `city` | нет | `string` | нет | — | Город доставки. |
| `comment` | нет | `string` | нет | — | Комментарий к заказу. |
| `country` | нет | `string` | нет | — | Страна доставки. |
| `district` | нет | `string` | нет | — | Район доставки. |
| `latitude` | нет | `number` | нет | format=`"double"` | Широта. |
| `longitude` | нет | `number` | нет | format=`"double"` | Долгота. |
| `provider_pvz_code` | нет | `string` | нет | — | Код пункта выдачи заказов 3PL-провайдера. |
| `pvz_code` | нет | `integer` | нет | format=`"int64"` | Код пункта выдачи заказов. |
| `region` | нет | `string` | нет | — | Регион доставки. |
| `zip_code` | нет | `string` | нет | — | Почтовый индекс получателя. |

### posting.v4.PostingFbsListResponse.Postings.DeliveryMethod

<a id="schema-posting-v4-postingfbslistresponse-postings-deliverymethod"></a>

Информация о способе доставки.

- Тип: `object`
- Nullable: **нет**
- Ограничения: —

#### Поля

| Поле | Required | Тип / вложенная ссылка | Nullable | Ограничения и enum | Description |
| --- | --- | --- | --- | --- | --- |
| `id` | нет | `integer` | нет | format=`"int64"` | Идентификатор способа доставки. |
| `name` | нет | `string` | нет | — | Название способа доставки. |
| `tpl_provider` | нет | `string` | нет | — | Служба доставки. |
| `tpl_provider_id` | нет | `integer` | нет | format=`"int64"` | Идентификатор службы доставки. |
| `warehouse` | нет | `string` | нет | — | Название склада. |
| `warehouse_id` | нет | `integer` | нет | format=`"int64"` | Идентификатор склада. |

### posting.v4.PostingFbsListResponse.Postings.ExternalOrder

<a id="schema-posting-v4-postingfbslistresponse-postings-externalorder"></a>

Информация о заказе с внешней платформы.

- Тип: `object`
- Nullable: **нет**
- Ограничения: —

#### Поля

| Поле | Required | Тип / вложенная ссылка | Nullable | Ограничения и enum | Description |
| --- | --- | --- | --- | --- | --- |
| `is_external` | нет | `boolean` | нет | — | `true`, если заказ с внешней платформы.<br> |
| `platform_name` | нет | `string` | нет | — | Название платформы, с которой сделали заказ. |

### posting.v4.PostingFbsListResponse.Postings.FinancialData

<a id="schema-posting-v4-postingfbslistresponse-postings-financialdata"></a>

Информация о стоимости товара, размере скидки, выплате и комиссии.

- Тип: `object`
- Nullable: **нет**
- Ограничения: —

#### Поля

| Поле | Required | Тип / вложенная ссылка | Nullable | Ограничения и enum | Description |
| --- | --- | --- | --- | --- | --- |
| `cluster_from` | нет | `string` | нет | — | Код региона, откуда отправляется заказ. |
| `cluster_to` | нет | `string` | нет | — | Код региона, куда доставляется заказ. |
| `products` | нет | array&lt;[`posting.v4.PostingFbsListResponse.Postings.FinancialData.Products`](#schema-posting-v4-postingfbslistresponse-postings-financialdata-products)&gt; | нет | — | Список товаров в заказе. |

### posting.v4.PostingFbsListResponse.Postings.FinancialData.Products

<a id="schema-posting-v4-postingfbslistresponse-postings-financialdata-products"></a>

- Тип: `object`
- Nullable: **нет**
- Ограничения: —

#### Поля

| Поле | Required | Тип / вложенная ссылка | Nullable | Ограничения и enum | Description |
| --- | --- | --- | --- | --- | --- |
| `actions` | нет | array&lt;`string`&gt; | нет | — | Список акций. |
| `commission` | нет | [`posting.v4.PostingFbsListResponse.Postings.FinancialData.Products.Commission`](#schema-posting-v4-postingfbslistresponse-postings-financialdata-products-commission) | нет | — | — |
| `customer_price` | нет | [`money.postingMoney`](#schema-money-postingmoney) | нет | — | — |
| `old_price` | нет | `number` | нет | format=`"double"` | Цена до учёта скидок. На карточке товара отображается зачёркнутой. |
| `payout` | нет | `number` | нет | format=`"double"` | Выплата продавцу. |
| `price` | нет | `number` | нет | format=`"double"` | Цена товара с учётом акций, кроме акций за счёт Ozon. |
| `product_id` | нет | `integer` | нет | format=`"int64"` | Идентификатор товара в системе Ozon — SKU. |
| `quantity` | нет | `integer` | нет | format=`"int64"` | Количество товара в отправлении. |
| `total_discount_percent` | нет | `number` | нет | format=`"double"` | Процент скидки. |
| `total_discount_value` | нет | `number` | нет | format=`"double"` | Сумма скидки. |

### posting.v4.PostingFbsListResponse.Postings.FinancialData.Products.Commission

<a id="schema-posting-v4-postingfbslistresponse-postings-financialdata-products-commission"></a>

Комиссия за товар.

- Тип: `object`
- Nullable: **нет**
- Ограничения: —

#### Поля

| Поле | Required | Тип / вложенная ссылка | Nullable | Ограничения и enum | Description |
| --- | --- | --- | --- | --- | --- |
| `amount` | нет | `number` | нет | format=`"double"` | Размер комиссии за товар. |
| `currency` | нет | `string` | нет | — | Код валюты, в которой рассчитывалась комиссия. |
| `percent` | нет | `integer` | нет | format=`"int64"` | Процент комиссии. |

### posting.v4.PostingFbsListResponse.Postings.LegalInfo

<a id="schema-posting-v4-postingfbslistresponse-postings-legalinfo"></a>

Юридическая информация о покупателе.

- Тип: `object`
- Nullable: **нет**
- Ограничения: —

#### Поля

| Поле | Required | Тип / вложенная ссылка | Nullable | Ограничения и enum | Description |
| --- | --- | --- | --- | --- | --- |
| `company_name` | нет | `string` | нет | — | Название компании. |
| `inn` | нет | `string` | нет | — | ИНН. |
| `kpp` | нет | `string` | нет | — | КПП. |

### posting.v4.PostingFbsListResponse.Postings.Optional

<a id="schema-posting-v4-postingfbslistresponse-postings-optional"></a>

Список товаров с дополнительными характеристиками.

- Тип: `object`
- Nullable: **нет**
- Ограничения: —

#### Поля

| Поле | Required | Тип / вложенная ссылка | Nullable | Ограничения и enum | Description |
| --- | --- | --- | --- | --- | --- |
| `products_with_possible_mandatory_mark` | нет | array&lt;`string`&gt; | нет | — | Список товаров с возможной маркировкой. |

### posting.v4.PostingFbsListResponse.Postings.Products

<a id="schema-posting-v4-postingfbslistresponse-postings-products"></a>

- Тип: `object`
- Nullable: **нет**
- Ограничения: —

#### Поля

| Поле | Required | Тип / вложенная ссылка | Nullable | Ограничения и enum | Description |
| --- | --- | --- | --- | --- | --- |
| `imei` | нет | array&lt;`string`&gt; | нет | — | Список IMEI мобильных устройств. |
| `is_blr_traceable` | нет | `boolean` | нет | — | `true`, если товар отслеживаемый.<br> |
| `is_marketplace_buyout` | нет | `boolean` | нет | — | `true`, если Ozon выкупил товар.<br><br>[Подробнее о выкупе товаров в Базе знаний продавца](https://seller-edu.ozon.ru/commissions-tariffs/commissions-tariffs-ozon/prodaji-tovarov-v-eaes-i-drugie-strany#какие-товары-выкупает-ozon)<br> |
| `name` | нет | `string` | нет | — | Название товара. |
| `offer_id` | нет | `string` | нет | — | Идентификатор товара в системе продавца — артикул. |
| `price` | нет | [`money.postingMoney`](#schema-money-postingmoney) | нет | — | — |
| `product_color` | нет | `string` | нет | — | Цвет товара. |
| `quantity` | нет | `integer` | нет | format=`"int32"` | Количество товара в отправлении. |
| `sku` | нет | `integer` | нет | format=`"int64"` | Идентификатор товара в системе Ozon — SKU. |
| `weight` | нет | `number` | нет | format=`"double"` | Вес товара в упаковке. |

### posting.v4.PostingFbsListResponse.Postings.Requirements

<a id="schema-posting-v4-postingfbslistresponse-postings-requirements"></a>

Товары, для которых нужна дополнительная информация.<br><br>Чтобы перевести отправление в следующий статус, передайте:<br>- страну-изготовителя; <br>- номер грузовой таможенной декларации (ГТД);<br>- регистрационный номер партии товара (РНПТ);<br>- маркировку «Честный знак»;<br>- другие маркировки;<br>- вес.<br>

- Тип: `object`
- Nullable: **нет**
- Ограничения: —

#### Поля

| Поле | Required | Тип / вложенная ссылка | Nullable | Ограничения и enum | Description |
| --- | --- | --- | --- | --- | --- |
| `products_requiring_change_country` | нет | array&lt;`string`&gt; | нет | — | Список идентификаторов товаров (SKU), для которых нужно изменить страну-изготовителя. Чтобы изменить страну-изготовителя, используйте методы [/v2/posting/fbs/product/country/list](#operation/PostingAPI_ListCountryProductFbsPostingV2) и [/v2/posting/fbs/product/country/set](#operation/PostingAPI_SetCountryProductFbsPostingV2). |
| `products_requiring_country` | нет | array&lt;`string`&gt; | нет | — | Список идентификаторов товаров (SKU), для которых нужно передать информацию о стране-изготовителе.<br><br>Для сборки отправления передайте информацию о стране-изготовителе для всех перечисленных товаров методом [/v2/posting/fbs/product/country/set](#operation/PostingAPI_SetCountryProductFbsPostingV2).<br> |
| `products_requiring_gtd` | нет | array&lt;`string`&gt; | нет | — | Список идентификаторов товаров (SKU), для которых нужно передать номера грузовой таможенной декларации (ГТД).<br><br>До сборки отправления передайте для всех перечисленных товаров номер грузовой таможенной декларации или информацию о том, <br>что номера нет, методом [/v6/fbs/posting/product/exemplar/set](#operation/PostingAPI_FbsPostingProductExemplarSetV6).<br> |
| `products_requiring_imei` | нет | array&lt;`string`&gt; | нет | — | Список идентификаторов товаров, для которых нужно передать IMEI. |
| `products_requiring_jw_uin` | нет | array&lt;`string`&gt; | нет | — | Список товаров, для которых нужно передать уникальный идентификационный номер (УИН) ювелирного изделия.<br><br>До сборки отправления передайте для всех перечисленных товаров УИН методом [/v6/fbs/posting/product/exemplar/set](#operation/PostingAPI_FbsPostingProductExemplarSetV6).<br> |
| `products_requiring_mandatory_mark` | нет | array&lt;`string`&gt; | нет | — | Список идентификаторов товаров (SKU), для которых нужно передать маркировку «Честный знак».<br><br>До сборки отправления передайте для всех перечисленных товаров маркировку «Честный знак» методом [/v6/fbs/posting/product/exemplar/set](#operation/PostingAPI_FbsPostingProductExemplarSetV6).<br> |
| `products_requiring_rnpt` | нет | array&lt;`string`&gt; | нет | — | Список идентификаторов товаров (SKU), для которых нужно передать регистрационный номер партии товара (РНПТ).<br><br>До сборки отправления передайте для всех перечисленных товаров РНПТ методом [/v6/fbs/posting/product/exemplar/set](#operation/PostingAPI_FbsPostingProductExemplarSetV6).<br> |
| `products_requiring_weight` | нет | array&lt;`string`&gt; | нет | — | Список товаров, для которых нужно передать вес. |

### posting.v4.PostingFbsListResponse.Postings.SortingCenter

<a id="schema-posting-v4-postingfbslistresponse-postings-sortingcenter"></a>

Информация о сортировочном центре, в который нужно привезти отправление. Для `integration_type_flow = hybrid_3pl_tracking`.<br>Если значение `null`, информацию получить не удалось.<br>

- Тип: `object`
- Nullable: **нет**
- Ограничения: —

#### Поля

| Поле | Required | Тип / вложенная ссылка | Nullable | Ограничения и enum | Description |
| --- | --- | --- | --- | --- | --- |
| `code` | нет | `string` | нет | — | Код сортировочного центра. |
| `name` | нет | `string` | нет | — | Название сортировочного центра. |

### posting.v4.PostingFbsListResponse.Postings.Tariffication

<a id="schema-posting-v4-postingfbslistresponse-postings-tariffication"></a>

Информация по тарификации отгрузки.

- Тип: `object`
- Nullable: **нет**
- Ограничения: —

#### Поля

| Поле | Required | Тип / вложенная ссылка | Nullable | Ограничения и enum | Description |
| --- | --- | --- | --- | --- | --- |
| `current_tariff_charge` | нет | [`money.Money.Current_tariff_charge`](#schema-money-money-current-tariff-charge) | нет | — | — |
| `current_tariff_min_charge` | нет | [`money.Money.Current_tariff_min_charge`](#schema-money-money-current-tariff-min-charge) | нет | — | — |
| `current_tariff_rate` | нет | `number` | нет | format=`"double"` | Процент тарификации. |
| `current_tariff_type` | нет | `string` | нет | — | Тип тарификации — скидка или надбавка. |
| `next_tariff_charge` | нет | [`money.Money.Next_tariff_charge`](#schema-money-money-next-tariff-charge) | нет | — | — |
| `next_tariff_min_charge` | нет | [`money.Money.Next_tariff_min_charge`](#schema-money-money-next-tariff-min-charge) | нет | — | — |
| `next_tariff_rate` | нет | `number` | нет | format=`"double"` | Процент, по которому будет тарифицироваться отправление через время из параметра `next_tariff_starts_at`. |
| `next_tariff_starts_at` | нет | `string` | нет | format=`"date-time"`; pattern=`" YYYY-MM-DDThh:mm:ss.mcsZ"` | Дата и время, когда начнёт применяться новый тариф. |
| `next_tariff_type` | нет | `string` | нет | — | Тип тарификации через время из параметра `next_tariff_starts_at` — скидка или надбавка. |

### posting.v4.PostingFbsListResponse.Postings.TarifficationStep

<a id="schema-posting-v4-postingfbslistresponse-postings-tarifficationstep"></a>

- Тип: `object`
- Nullable: **нет**
- Ограничения: —

#### Поля

| Поле | Required | Тип / вложенная ссылка | Nullable | Ограничения и enum | Description |
| --- | --- | --- | --- | --- | --- |
| `min_charge` | нет | [`money.Money.Current_tariff_min_charge`](#schema-money-money-current-tariff-min-charge) | нет | — | — |
| `tariff_charge` | нет | [`money.Money.Current_tariff_charge`](#schema-money-money-current-tariff-charge) | нет | — | — |
| `tariff_deadline_at` | нет | `string` | нет | format=`"date-time"` | Дата и время окончания этапа тарификации. После этой даты автоматически начинается следующий этап. |
| `tariff_rate` | нет | `number` | нет | format=`"double"` | Процент скидки или надбавки. |
| `tariff_type` | нет | `string` | нет | — | Тип тарификации. |

### posting.v4.PostingFbsUnfulfilledListRequest

<a id="schema-posting-v4-postingfbsunfulfilledlistrequest"></a>

- Тип: `object`
- Nullable: **нет**
- Ограничения: —

#### Поля

| Поле | Required | Тип / вложенная ссылка | Nullable | Ограничения и enum | Description |
| --- | --- | --- | --- | --- | --- |
| `cursor` | нет | `string` | нет | — | Указатель для выборки следующих данных. |
| `filter` | нет | [`posting.v4.PostingFbsUnfulfilledListRequest.Filter`](#schema-posting-v4-postingfbsunfulfilledlistrequest-filter) | нет | — | — |
| `limit` | нет | `integer` | нет | format=`"int64"`; minimum=`1`; maximum=`100` | Количество значений в ответе. |
| `sort_dir` | нет | [`posting.v4.PostingFbsUnfulfilledListRequest.SortDir.Enum`](#schema-posting-v4-postingfbsunfulfilledlistrequest-sortdir-enum) | нет | — | — |
| `translit` | нет | `boolean` | нет | — | `true`, чтобы включить транслитерацию адреса из кириллицы в латиницу.<br> |
| `with` | нет | [`posting.v4.PostingFbsUnfulfilledListRequest.With`](#schema-posting-v4-postingfbsunfulfilledlistrequest-with) | нет | — | — |

### posting.v4.PostingFbsUnfulfilledListRequest.Filter

<a id="schema-posting-v4-postingfbsunfulfilledlistrequest-filter"></a>

Фильтр запроса.<br><br>Используйте фильтр по времени сборки — `cutoff` или по дате передачи отправления в доставку — `delivering_date`.<br>Если использовать их вместе, в ответе вернётся ошибка.<br><br>Чтобы использовать фильтр по времени сборки, заполните поля `cutoff_from` и `cutoff_to`.<br><br>Чтобы использовать фильтр по дате передачи отправления в доставку, заполните поля `delivering_date_from` и `delivering_date_to`.<br>

- Тип: `object`
- Nullable: **нет**
- Ограничения: —

#### Поля

| Поле | Required | Тип / вложенная ссылка | Nullable | Ограничения и enum | Description |
| --- | --- | --- | --- | --- | --- |
| `cutoff_from` | нет | `string` | нет | format=`"date-time"`; pattern=`" YYYY-MM-DDThh:mm:ss.mcsZ"` | Время, до которого продавцу нужно собрать заказ. Начало периода. |
| `cutoff_to` | нет | `string` | нет | format=`"date-time"`; pattern=`" YYYY-MM-DDThh:mm:ss.mcsZ"` | Время, до которого продавцу нужно собрать заказ. Конец периода. |
| `delivering_date_from` | нет | `string` | нет | format=`"date-time"` | Минимальная дата передачи отправления в доставку. |
| `delivering_date_to` | нет | `string` | нет | format=`"date-time"` | Максимальная дата передачи отправления в доставку. |
| `delivery_method_ids` | нет | array&lt;`string`&gt; | нет | maxItems=`1000` | Идентификатор способа доставки. Можно получить с помощью метода [/v1/delivery-method/list](#operation/WarehouseAPI_DeliveryMethodList). |
| `last_changed_status_date` | нет | [`posting.v4.PostingFbsUnfulfilledListRequest.Filter.LastChangedStatusDate`](#schema-posting-v4-postingfbsunfulfilledlistrequest-filter-lastchangedstatusdate) | нет | — | — |
| `provider_ids` | нет | array&lt;`string`&gt; | нет | maxItems=`1000` | Идентификатор службы доставки. Можно получить с помощью метода [/v1/delivery-method/list](#operation/WarehouseAPI_DeliveryMethodList). |
| `statuses` | нет | array&lt;`string`&gt; | нет | — | Статус отправления:<br>- `acceptance_in_progress` — идёт приёмка;<br>- `awaiting_approve` — ожидает подтверждения;<br>- `awaiting_packaging` — ожидает упаковки;<br>- `awaiting_registration` — ожидает регистрации;<br>- `awaiting_deliver` — ожидает отгрузки;<br>- `arbitration` — арбитраж;<br>- `client_arbitration` — клиентский арбитраж доставки;<br>- `delivering` — доставляется;<br>- `driver_pickup` — у водителя;<br>- `not_accepted` — не принято на сортировочном центре.<br> |
| `warehouse_ids` | нет | array&lt;`string`&gt; | нет | maxItems=`1000` | Идентификатор склада. Можно получить с помощью метода [/v1/warehouse/list](#operation/WarehouseAPI_WarehouseList). |

### posting.v4.PostingFbsUnfulfilledListRequest.Filter.LastChangedStatusDate

<a id="schema-posting-v4-postingfbsunfulfilledlistrequest-filter-lastchangedstatusdate"></a>

Период, в который последний раз изменялся статус отправления.

- Тип: `object`
- Nullable: **нет**
- Ограничения: —

#### Поля

| Поле | Required | Тип / вложенная ссылка | Nullable | Ограничения и enum | Description |
| --- | --- | --- | --- | --- | --- |
| `from` | нет | `string` | нет | format=`"date-time"` | Дата начала периода. |
| `to` | нет | `string` | нет | format=`"date-time"` | Дата окончания периода. |

### posting.v4.PostingFbsUnfulfilledListRequest.SortDir.Enum

<a id="schema-posting-v4-postingfbsunfulfilledlistrequest-sortdir-enum"></a>

Направление сортировки:<br>- `ASC` — по возрастанию;<br>- `DESC` — по убыванию.<br>

- Тип: `string`
- Nullable: **нет**
- Ограничения: enum=`"ASC"`, `"DESC"`

#### Поля

| Поле | Required | Тип / вложенная ссылка | Nullable | Ограничения и enum | Description |
| --- | --- | --- | --- | --- | --- |
| — | — | — | — | — | — |

### posting.v4.PostingFbsUnfulfilledListRequest.With

<a id="schema-posting-v4-postingfbsunfulfilledlistrequest-with"></a>

Дополнительные поля, которые нужно добавить в ответ.

- Тип: `object`
- Nullable: **нет**
- Ограничения: —

#### Поля

| Поле | Required | Тип / вложенная ссылка | Nullable | Ограничения и enum | Description |
| --- | --- | --- | --- | --- | --- |
| `analytics_data` | нет | `boolean` | нет | — | `true`, чтобы добавить в ответ данные аналитики.<br> |
| `barcodes` | нет | `boolean` | нет | — | `true`, чтобы добавить в ответ штрихкоды отправления.<br> |
| `financial_data` | нет | `boolean` | нет | — | `true`, чтобы добавить в ответ финансовые данные.<br> |
| `legal_info` | нет | `boolean` | нет | — | `true`, чтобы добавить в ответ юридическую информацию.<br> |

### posting.v4.PostingFbsUnfulfilledListResponse

<a id="schema-posting-v4-postingfbsunfulfilledlistresponse"></a>

- Тип: `object`
- Nullable: **нет**
- Ограничения: —

#### Поля

| Поле | Required | Тип / вложенная ссылка | Nullable | Ограничения и enum | Description |
| --- | --- | --- | --- | --- | --- |
| `count` | нет | `integer` | нет | format=`"int64"` | Количество отправлений в ответе. |
| `cursor` | нет | `string` | нет | — | Указатель для выборки следующих данных. |
| `has_next` | нет | `boolean` | нет | — | `true`, если в ответе вернулись не все отправления.<br> |
| `postings` | нет | array&lt;[`posting.v4.PostingFbsUnfulfilledListResponse.Postings`](#schema-posting-v4-postingfbsunfulfilledlistresponse-postings)&gt; | нет | — | Список отправлений. |

### posting.v4.PostingFbsUnfulfilledListResponse.Postings

<a id="schema-posting-v4-postingfbsunfulfilledlistresponse-postings"></a>

- Тип: `object`
- Nullable: **нет**
- Ограничения: —

#### Поля

| Поле | Required | Тип / вложенная ссылка | Nullable | Ограничения и enum | Description |
| --- | --- | --- | --- | --- | --- |
| `addressee` | нет | [`posting.v4.PostingFbsUnfulfilledListResponse.Postings.Addressee`](#schema-posting-v4-postingfbsunfulfilledlistresponse-postings-addressee) | нет | — | — |
| `analytics_data` | нет | [`posting.v4.PostingFbsUnfulfilledListResponse.Postings.AnalyticsData`](#schema-posting-v4-postingfbsunfulfilledlistresponse-postings-analyticsdata) | нет | — | — |
| `available_actions` | нет | array&lt;`string`&gt; | нет | — | Доступные действия и информация об отправлении:<br>- `arbitration` — открыть спор;<br>- `awaiting_delivery` — перевести в статус «Ожидает отгрузки»;<br>- `can_create_chat` — начать чат с покупателем;<br>- `cancel` — отменить отправление;<br>- `click_track_number` — просмотреть по трек-номеру историю изменения статусов в личном кабинете;<br>- `customer_phone_available` — телефон покупателя;<br>- `has_weight_products` — весовые товары в отправлении;<br>- `hide_region_and_city` — скрыть регион и город покупателя в отчёте;<br>- `invoice_get` —  получить информацию из счёта-фактуры;<br>- `invoice_send` — создать счёт-фактуру;<br>- `invoice_update` — отредактировать счёт-фактуру;<br>- `label_download_big` — скачать большую этикетку;<br>- `label_download_small` — скачать маленькую этикетку;<br>- `label_download` — скачать этикетку;<br>- `non_int_delivered` — перевести в статус «Условно доставлен»;<br>- `non_int_delivering` — перевести в статус «Доставляется»;<br>- `non_int_last_mile` — перевести в статус «Курьер в пути»;<br>- `product_cancel` — отменить часть товаров в отправлении;<br>- `set_cutoff` — укажите дату отгрузки методом [/v1/posting/cutoff/set](#operation/PostingAPI_SetPostingCutoff) не позже даты в параметре `shipment_date`;<br>- `set_timeslot` — изменить время доставки покупателю;<br>- `set_track_number` — указать или изменить трек-номер;<br>- `ship_async_in_process` — отправление собирается;<br>- `ship_async_retry` — собрать отправление повторно после ошибки сборки;<br>- `ship_async` — собрать отправление;<br>- `ship_with_additional_info` — заполните дополнительную информацию методом [/v6/fbs/posting/product/exemplar/set](https://docs.ozon.ru/api/seller/#operation/PostingAPI_FbsPostingProductExemplarSetV6);<br>- `ship` — собрать отправление;<br>- `update_cis` — изменить дополнительную информацию.<br> |
| `barcodes` | нет | [`posting.v4.PostingFbsUnfulfilledListResponse.Postings.Barcodes`](#schema-posting-v4-postingfbsunfulfilledlistresponse-postings-barcodes) | нет | — | — |
| `cancellation` | нет | [`posting.v4.PostingFbsUnfulfilledListResponse.Postings.Cancellation`](#schema-posting-v4-postingfbsunfulfilledlistresponse-postings-cancellation) | нет | — | — |
| `customer` | нет | [`posting.v4.PostingFbsUnfulfilledListResponse.Postings.Customer`](#schema-posting-v4-postingfbsunfulfilledlistresponse-postings-customer) | нет | — | — |
| `container` | нет | [`posting.v4.PostingFbsUnfulfilledListResponse.Postings.Container`](#schema-posting-v4-postingfbsunfulfilledlistresponse-postings-container) | нет | — | — |
| `container_sort_type` | нет | `string` | нет | — | Тип сортировки грузоместа:<br>  - `SORT` — сортируемый;<br>  - `NON-SORT` — несортируемый.<br> |
| `delivering_date` | нет | `string` | нет | format=`"date-time"` | Дата передачи отправления в доставку. |
| `delivery_method` | нет | [`posting.v4.PostingFbsUnfulfilledListResponse.Postings.DeliveryMethod`](#schema-posting-v4-postingfbsunfulfilledlistresponse-postings-deliverymethod) | нет | — | — |
| `delivery_schema` | нет | `string` | нет | — | Схема доставки:<br>- `SDS` — идентификатор единого SKU;<br>- `FBO` — идентификатор товара, который продаётся со склада Ozon;<br>- `FBS` — идентификатор товара, который продаётся со склада FBS;<br>- `Crossborder` — идентификатор товара, который продаётся из-за границы.<br> |
| `destination_place_id` | нет | `integer` | нет | format=`"int64"` | Идентификатор места назначения. |
| `destination_place_name` | нет | `string` | нет | — | Название места назначения. |
| `external_order` | нет | [`posting.v4.PostingFbsUnfulfilledListResponse.Postings.ExternalOrder`](#schema-posting-v4-postingfbsunfulfilledlistresponse-postings-externalorder) | нет | — | — |
| `financial_data` | нет | [`posting.v4.PostingFbsUnfulfilledListResponse.Postings.FinancialData`](#schema-posting-v4-postingfbsunfulfilledlistresponse-postings-financialdata) | нет | — | — |
| `in_process_at` | нет | `string` | нет | format=`"date-time"` | Дата и время начала обработки отправления. |
| `integration_type_flow` | нет | `string` | нет | — | Процесс обработки отправления:<br>- `ozon` — доставка силами Ozon;<br>- `aggregator` — доставка внешней службой, Ozon регистрирует заказ;<br>- `non_integrated` — доставка силами продавца;<br>- `3pl_tracking` — доставка внешней службой, продавец регистрирует заказ;<br>- `hybrid` — гибридная интеграция;<br>- `hybrid_aggregator` — гибридная интеграция с доставкой внешней службой, Ozon регистрирует заказ;<br>- `hybrid_non_integrated` — гибридная интеграция с доставкой силами продавца;<br>- `hybrid_3pl_tracking` — гибридная интеграция с доставкой внешней службой, продавец регистрирует заказ;<br>- `click_and_collect` — бронирование в магазине партнёра;<br>- `FBP` — доставка с партнёрских складов Ozon.<br> |
| `is_click_and_collect` | нет | `boolean` | нет | — | `true`, если отправление доставляется методом «Самовывоз из магазина».<br> |
| `is_express` | нет | `boolean` | нет | — | `true`, если использовалась быстрая доставка Ozon Express.<br> |
| `is_multibox` | нет | `boolean` | нет | — | Признак, что в отправлении есть многокоробочный товар и нужно передать количество коробок для него:<br><br>- `true` — до сборки передайте количество коробок через метод [/v3/posting/multiboxqty/set](#operation/PostingAPI_PostingMultiBoxQtySetV3).<br>- `false` — отправление собрано с указанием количества коробок в параметре `multi_box_qty` или в отправлении нет многокоробочного товара.<br> |
| `is_presortable` | нет | `boolean` | нет | — | `true`, если товар пересорт.<br> |
| `legal_info` | нет | [`posting.v4.PostingFbsUnfulfilledListResponse.Postings.LegalInfo`](#schema-posting-v4-postingfbsunfulfilledlistresponse-postings-legalinfo) | нет | — | — |
| `multi_box_qty` | нет | `integer` | нет | format=`"int32"` | Количество коробок, в которые упакован товар. |
| `optional` | нет | [`posting.v4.PostingFbsUnfulfilledListResponse.Postings.Optional`](#schema-posting-v4-postingfbsunfulfilledlistresponse-postings-optional) | нет | — | — |
| `order_id` | нет | `integer` | нет | format=`"int64"` | Идентификатор заказа, к которому относится отправление. |
| `order_number` | нет | `string` | нет | — | Номер заказа, к которому относится отправление. |
| `parent_posting_number` | нет | `string` | нет | — | Номер родительского отправления, в результате разделения которого появилось текущее. |
| `pickup_code_verified_at` | нет | `string` | нет | format=`"date-time"` | Дата и время успешной валидации кода курьера. Проверьте код курьера методом [/v1/posting/fbs/pick-up-code/verify](#operation/PostingAPI_PostingFBSPickupCodeVerify). |
| `posting_number` | нет | `string` | нет | — | Номер отправления. |
| `products` | нет | array&lt;[`posting.v4.PostingFbsUnfulfilledListResponse.Postings.Products`](#schema-posting-v4-postingfbsunfulfilledlistresponse-postings-products)&gt; | нет | — | Список товаров в отправлении. |
| `prr_option` | нет | `string` | нет | — | Код услуги погрузочно-разгрузочных работ:<br>- `lift` — подъём на лифте;<br>- `stairs` — подъём по лестнице;<br>- `none` — покупатель отказался от услуги, поднимать товары не нужно;<br>- `delivery_default` — доставка включена в стоимость, по условиям оферты нужно доставить товар на этаж.<br><br>Для КГТ-отправлений с доставкой силами продавца или интегрированной службой.<br> |
| `quantum_id` | нет | `integer` | нет | format=`"int64"` | Идентификатор эконом-товара. |
| `require_blr_traceable_attrs` | нет | `boolean` | нет | — | `true`, если нужно заполнить атрибуты отслеживаемости.<br> |
| `requirements` | нет | [`posting.v4.PostingFbsUnfulfilledListResponse.Postings.Requirements`](#schema-posting-v4-postingfbsunfulfilledlistresponse-postings-requirements) | нет | — | — |
| `shipment_date` | нет | `string` | нет | format=`"date-time"` | Дата и время, до которой нужно собрать отправление. Показываем рекомендованное время отгрузки. По истечении этого времени начнёт применяться новый тариф, информацию о нём получите в поле `tariffication`. |
| `shipment_date_without_delay` | нет | `string` | нет | format=`"date-time"` | Дата и время отгрузки без просрочки. |
| `sorting_center` | нет | [`posting.v4.PostingFbsUnfulfilledListResponse.Postings.SortingCenter`](#schema-posting-v4-postingfbsunfulfilledlistresponse-postings-sortingcenter) | нет | — | — |
| `status` | нет | `string` | нет | — | Статус отправления:<br>- `acceptance_in_progress` — идёт приёмка;<br>- `arbitration` — арбитраж;<br>- `awaiting_approve` — ожидает подтверждения;<br>- `awaiting_deliver` — ожидает отгрузки;<br>- `awaiting_packaging` — ожидает упаковки;<br>- `awaiting_registration` — ожидает регистрации;<br>- `awaiting_verification` — создано;<br>- `cancelled` — отменено;<br>- `cancelled_from_split_pending` — отменено из-за разделения отправления;<br>- `client_arbitration` — клиентский арбитраж доставки;<br>- `delivering` — доставляется;<br>- `driver_pickup` — у водителя;<br>- `not_accepted` — не принято на сортировочном центре.<br> |
| `substatus` | нет | `string` | нет | — | Подстатус отправления:<br>- `posting_acceptance_in_progress`— идёт приёмка;<br>- `posting_in_arbitration` — арбитраж;<br>- `posting_created` — создано;<br>- `posting_in_carriage` — в перевозке;<br>- `posting_not_in_carriage` — не добавлено в перевозку;<br>- `posting_registered` — зарегистрировано;<br>- `posting_transferring_to_delivery`, если `status=awaiting_deliver` — передаётся в доставку;<br>- `posting_awaiting_passport_data` — ожидает паспортных данных;<br>- `posting_created` — создано;<br>- `posting_awaiting_registration` — ожидает регистрации;<br>- `posting_registration_error` — ошибка регистрации;<br>- `posting_transferring_to_delivery`, если `status=awaiting_registration` — передаётся курьеру;<br>- `posting_split_pending` — создано;<br>- `posting_canceled` — отменено;<br>- `posting_in_client_arbitration` — клиентский арбитраж доставки;<br>- `posting_delivered` — доставлено;<br>- `posting_received` — получено;<br>- `posting_conditionally_delivered` — условно доставлено;<br>- `posting_in_courier_service` — курьер в пути;<br>- `posting_in_pickup_point` — в пункте выдачи;<br>- `posting_on_way_to_city` — в пути в ваш город;<br>- `posting_on_way_to_pickup_point` — в пути в пункт выдачи;<br>- `posting_returned_to_warehouse` — возвращено на склад;<br>- `posting_transferred_to_courier_service` — передаётся в службу доставки;<br>- `posting_driver_pick_up` — у водителя;<br>- `posting_not_in_sort_center` — не принято на сортировочном центре;<br>- `ship_failed` — сборка не удалась.<br> |
| `tariffication` | нет | [`posting.v4.PostingFbsUnfulfilledListResponse.Postings.Tariffication`](#schema-posting-v4-postingfbsunfulfilledlistresponse-postings-tariffication) | нет | — | — |
| `tariffication_steps` | нет | array&lt;[`posting.v4.PostingFbsUnfulfilledListResponse.Postings.TarifficationStep`](#schema-posting-v4-postingfbsunfulfilledlistresponse-postings-tarifficationstep)&gt; | нет | — | Этапы тарификации. |
| `tpl_integration_type` | нет | `string` | нет | — | Тип интеграции со службой доставки:<br>  - `ozon` — доставка службой Ozon;<br>  - `3pl_tracking` — доставка интегрированной службой;<br>  - `non_integrated` — доставка сторонней службой;<br>  - `aggregator` — доставка через партнёрскую доставку Ozon;<br>  - `hybryd` — схема доставки Почты России.<br> |
| `tracking_number` | нет | `string` | нет | — | Трек-номер отправления. |
| `volume_weight` | нет | `number` | нет | format=`"double"` | Объёмный вес товара. |

### posting.v4.PostingFbsUnfulfilledListResponse.Postings.Addressee

<a id="schema-posting-v4-postingfbsunfulfilledlistresponse-postings-addressee"></a>

Контактные данные получателя.

- Тип: `object`
- Nullable: **нет**
- Ограничения: —

#### Поля

| Поле | Required | Тип / вложенная ссылка | Nullable | Ограничения и enum | Description |
| --- | --- | --- | --- | --- | --- |
| `name` | нет | `string` | нет | — | Имя получателя. |

### posting.v4.PostingFbsUnfulfilledListResponse.Postings.AnalyticsData

<a id="schema-posting-v4-postingfbsunfulfilledlistresponse-postings-analyticsdata"></a>

Данные аналитики.

- Тип: `object`
- Nullable: **нет**
- Ограничения: —

#### Поля

| Поле | Required | Тип / вложенная ссылка | Nullable | Ограничения и enum | Description |
| --- | --- | --- | --- | --- | --- |
| `city` | нет | `string` | нет | — | Город доставки. Только для отправлений rFBS и продавцов из СНГ. |
| `client_delivery_date_begin` | нет | `string` | нет | format=`"date-time"` | Дата и время начала доставки. Только для отправлений, оформленных через [Ozon Доставку](#tag/OzonLogistics). |
| `client_delivery_date_end` | нет | `string` | нет | format=`"date-time"` | Ожидаемая дата, до которой заказ будет доставлен. Только для отправлений, оформленных через [Ozon Доставку](#tag/OzonLogistics). |
| `delivery_date_begin` | нет | `string` | нет | format=`"date-time"` | Дата и время начала доставки. |
| `delivery_date_end` | нет | `string` | нет | format=`"date-time"` | Дата и время конца доставки. |
| `delivery_type` | нет | `string` | нет | — | Способ доставки. |
| `is_legal` | нет | `boolean` | нет | — | `true`, если получатель юридическое лицо.<br> |
| `is_premium` | нет | `boolean` | нет | — | `true`, если у получателя есть подписка Premium.<br> |
| `payment_type_group_name` | нет | `string` | нет | — | Способ оплаты: <br>- `картой онлайн`;<br>- `карта Ozon Банка`;<br>- `автосписание с карты Ozon Банка при выдаче`;<br>- `сохранённой картой при получении`;<br>- `Система Быстрых Платежей`;<br>- `Ozon Рассрочка`;<br>- `оплата на расчётный счёт`;<br>- `SberPay`;<br>- `предоплата на стороне внешнего продавца`.<br> |
| `region` | нет | `string` | нет | — | Регион доставки. Только для отправлений rFBS. |
| `tpl_provider` | нет | `string` | нет | — | Служба доставки. |
| `tpl_provider_id` | нет | `integer` | нет | format=`"int64"` | Идентификатор службы доставки. |
| `warehouse` | нет | `string` | нет | — | Название склада отправки заказа. |
| `warehouse_id` | нет | `integer` | нет | format=`"int64"` | Идентификатор склада. |

### posting.v4.PostingFbsUnfulfilledListResponse.Postings.Barcodes

<a id="schema-posting-v4-postingfbsunfulfilledlistresponse-postings-barcodes"></a>

Штрихкоды отправления.

- Тип: `object`
- Nullable: **нет**
- Ограничения: —

#### Поля

| Поле | Required | Тип / вложенная ссылка | Nullable | Ограничения и enum | Description |
| --- | --- | --- | --- | --- | --- |
| `lower_barcode` | нет | `string` | нет | — | Нижний штрихкод на маркировке отправления. |
| `upper_barcode` | нет | `string` | нет | — | Верхний штрихкод на маркировке отправления. |

### posting.v4.PostingFbsUnfulfilledListResponse.Postings.Cancellation

<a id="schema-posting-v4-postingfbsunfulfilledlistresponse-postings-cancellation"></a>

Информация об отмене.

- Тип: `object`
- Nullable: **нет**
- Ограничения: —

#### Поля

| Поле | Required | Тип / вложенная ссылка | Nullable | Ограничения и enum | Description |
| --- | --- | --- | --- | --- | --- |
| `affect_cancellation_rating` | нет | `boolean` | нет | — | `true`, если отмена влияет на рейтинг продавца.<br> |
| `cancel_reason` | нет | `string` | нет | — | Причина отмены. |
| `cancel_reason_id` | нет | `integer` | нет | format=`"int64"` | Идентификатор причины отмены отправления. |
| `cancellation_initiator` | нет | `string` | нет | — | Инициатор отмены:<br>- `Продавец`,<br>- `Клиент`,<br>- `Покупатель`,<br>- `Ozon`,<br>- `Система`,<br>- `Служба доставки`.<br> |
| `cancellation_type` | нет | `string` | нет | — | Тип отмены:<br>- `seller` — отменено продавцом;<br>- `client` или `customer` — отменено покупателем;<br>- `ozon` — отменено Ozon;<br>- `system` — отменено системой;<br>- `delivery` — отменено службой доставки.<br> |
| `cancelled_after_ship` | нет | `boolean` | нет | — | `true`, если отмена произошла после сборки отправления.<br> |

### posting.v4.PostingFbsUnfulfilledListResponse.Postings.Container

<a id="schema-posting-v4-postingfbsunfulfilledlistresponse-postings-container"></a>

Информация о грузоместе.

- Тип: `object`
- Nullable: **нет**
- Ограничения: —

#### Поля

| Поле | Required | Тип / вложенная ссылка | Nullable | Ограничения и enum | Description |
| --- | --- | --- | --- | --- | --- |
| `cargo_type` | нет | [`posting.v4.PostingFbsUnfulfilledListResponse.Postings.Container.CargoType.Enum`](#schema-posting-v4-postingfbsunfulfilledlistresponse-postings-container-cargotype-enum) | нет | — | Тип грузоместа. |
| `container_date` | нет | `string` | нет | — | Дата создания грузоместа в часовом поясе склада. |
| `container_id` | нет | `integer` | нет | format=`"int64"` | Идентификатор грузоместа. |
| `container_number` | нет | `integer` | нет | format=`"int32"` | Порядковый номер грузоместа. |

### posting.v4.PostingFbsUnfulfilledListResponse.Postings.Container.CargoType.Enum

<a id="schema-posting-v4-postingfbsunfulfilledlistresponse-postings-container-cargotype-enum"></a>

Тип грузоместа: <br>  - `BOX` — коробка;<br>  - `PALLET` — палета.<br>

- Тип: `string`
- Nullable: **нет**
- Ограничения: default=`"BOX"`; enum=`"BOX"`, `"PALLET"`

#### Поля

| Поле | Required | Тип / вложенная ссылка | Nullable | Ограничения и enum | Description |
| --- | --- | --- | --- | --- | --- |
| — | — | — | — | — | — |

### posting.v4.PostingFbsUnfulfilledListResponse.Postings.Customer

<a id="schema-posting-v4-postingfbsunfulfilledlistresponse-postings-customer"></a>

Информация о покупателе.

- Тип: `object`
- Nullable: **нет**
- Ограничения: —

#### Поля

| Поле | Required | Тип / вложенная ссылка | Nullable | Ограничения и enum | Description |
| --- | --- | --- | --- | --- | --- |
| `address` | нет | [`posting.v4.PostingFbsUnfulfilledListResponse.Postings.Customer.Address`](#schema-posting-v4-postingfbsunfulfilledlistresponse-postings-customer-address) | нет | — | — |
| `customer_email` | нет | `string` | нет | — | Электронная почта покупателя. |
| `customer_id` | нет | `integer` | нет | format=`"int64"` | Идентификатор покупателя. |
| `name` | нет | `string` | нет | — | Имя покупателя. |
| `phone` | нет | `string` | нет | — | Подменный контактный телефон покупателя. |

### posting.v4.PostingFbsUnfulfilledListResponse.Postings.Customer.Address

<a id="schema-posting-v4-postingfbsunfulfilledlistresponse-postings-customer-address"></a>

Информация об адресе доставки.

- Тип: `object`
- Nullable: **нет**
- Ограничения: —

#### Поля

| Поле | Required | Тип / вложенная ссылка | Nullable | Ограничения и enum | Description |
| --- | --- | --- | --- | --- | --- |
| `address_tail` | нет | `string` | нет | — | Адрес в текстовом формате. |
| `city` | нет | `string` | нет | — | Город доставки. |
| `comment` | нет | `string` | нет | — | Комментарий к заказу. |
| `country` | нет | `string` | нет | — | Страна доставки. |
| `district` | нет | `string` | нет | — | Район доставки. |
| `latitude` | нет | `number` | нет | format=`"double"` | Широта. |
| `longitude` | нет | `number` | нет | format=`"double"` | Долгота. |
| `provider_pvz_code` | нет | `string` | нет | — | Код пункта выдачи заказов 3PL-провайдера. |
| `pvz_code` | нет | `integer` | нет | format=`"int64"` | Код пункта выдачи заказов. |
| `region` | нет | `string` | нет | — | Регион доставки. |
| `zip_code` | нет | `string` | нет | — | Почтовый индекс получателя. |

### posting.v4.PostingFbsUnfulfilledListResponse.Postings.DeliveryMethod

<a id="schema-posting-v4-postingfbsunfulfilledlistresponse-postings-deliverymethod"></a>

Информация о способе доставки.

- Тип: `object`
- Nullable: **нет**
- Ограничения: —

#### Поля

| Поле | Required | Тип / вложенная ссылка | Nullable | Ограничения и enum | Description |
| --- | --- | --- | --- | --- | --- |
| `id` | нет | `integer` | нет | format=`"int64"` | Идентификатор способа доставки. |
| `name` | нет | `string` | нет | — | Название способа доставки. |
| `tpl_provider` | нет | `string` | нет | — | Служба доставки. |
| `tpl_provider_id` | нет | `integer` | нет | format=`"int64"` | Идентификатор службы доставки. |
| `warehouse` | нет | `string` | нет | — | Название склада. |
| `warehouse_id` | нет | `integer` | нет | format=`"int64"` | Идентификатор склада. |

### posting.v4.PostingFbsUnfulfilledListResponse.Postings.ExternalOrder

<a id="schema-posting-v4-postingfbsunfulfilledlistresponse-postings-externalorder"></a>

Информация о заказе с внешней платформы.

- Тип: `object`
- Nullable: **нет**
- Ограничения: —

#### Поля

| Поле | Required | Тип / вложенная ссылка | Nullable | Ограничения и enum | Description |
| --- | --- | --- | --- | --- | --- |
| `is_external` | нет | `boolean` | нет | — | `true`, если заказ с внешней платформы.<br> |
| `platform_name` | нет | `string` | нет | — | Название платформы, с которой сделали заказ. |

### posting.v4.PostingFbsUnfulfilledListResponse.Postings.FinancialData

<a id="schema-posting-v4-postingfbsunfulfilledlistresponse-postings-financialdata"></a>

Информация о стоимости товара, размере скидки, выплате и комиссии.

- Тип: `object`
- Nullable: **нет**
- Ограничения: —

#### Поля

| Поле | Required | Тип / вложенная ссылка | Nullable | Ограничения и enum | Description |
| --- | --- | --- | --- | --- | --- |
| `cluster_from` | нет | `string` | нет | — | Код региона, откуда отправляется заказ. |
| `cluster_to` | нет | `string` | нет | — | Код региона, куда доставляется заказ. |
| `products` | нет | array&lt;[`posting.v4.PostingFbsUnfulfilledListResponse.Postings.FinancialData.Products`](#schema-posting-v4-postingfbsunfulfilledlistresponse-postings-financialdata-products)&gt; | нет | — | Список товаров в заказе. |

### posting.v4.PostingFbsUnfulfilledListResponse.Postings.FinancialData.Products

<a id="schema-posting-v4-postingfbsunfulfilledlistresponse-postings-financialdata-products"></a>

- Тип: `object`
- Nullable: **нет**
- Ограничения: —

#### Поля

| Поле | Required | Тип / вложенная ссылка | Nullable | Ограничения и enum | Description |
| --- | --- | --- | --- | --- | --- |
| `actions` | нет | array&lt;`string`&gt; | нет | — | Список акций. |
| `commission` | нет | [`posting.v4.PostingFbsUnfulfilledListResponse.Postings.FinancialData.Products.Commission`](#schema-posting-v4-postingfbsunfulfilledlistresponse-postings-financialdata-products-commission) | нет | — | — |
| `customer_price` | нет | [`money.postingMoney`](#schema-money-postingmoney) | нет | — | — |
| `old_price` | нет | `number` | нет | format=`"double"` | Цена до учёта скидок. На карточке товара отображается зачёркнутой. |
| `payout` | нет | `number` | нет | format=`"double"` | Выплата продавцу. |
| `price` | нет | `number` | нет | format=`"double"` | Цена товара с учётом акций, кроме акций за счёт Ozon. |
| `product_id` | нет | `integer` | нет | format=`"int64"` | Идентификатор товара в системе Ozon — SKU. |
| `quantity` | нет | `integer` | нет | format=`"int64"` | Количество товара в отправлении. |
| `total_discount_percent` | нет | `number` | нет | format=`"double"` | Процент скидки. |
| `total_discount_value` | нет | `number` | нет | format=`"double"` | Сумма скидки. |

### posting.v4.PostingFbsUnfulfilledListResponse.Postings.FinancialData.Products.Commission

<a id="schema-posting-v4-postingfbsunfulfilledlistresponse-postings-financialdata-products-commission"></a>

Комиссия за товар.

- Тип: `object`
- Nullable: **нет**
- Ограничения: —

#### Поля

| Поле | Required | Тип / вложенная ссылка | Nullable | Ограничения и enum | Description |
| --- | --- | --- | --- | --- | --- |
| `amount` | нет | `number` | нет | format=`"double"` | Размер комиссии за товар. |
| `currency` | нет | `string` | нет | — | Код валюты, в которой рассчитывалась комиссия. |
| `percent` | нет | `integer` | нет | format=`"int64"` | Процент комиссии. |

### posting.v4.PostingFbsUnfulfilledListResponse.Postings.LegalInfo

<a id="schema-posting-v4-postingfbsunfulfilledlistresponse-postings-legalinfo"></a>

Юридическая информация о покупателе.

- Тип: `object`
- Nullable: **нет**
- Ограничения: —

#### Поля

| Поле | Required | Тип / вложенная ссылка | Nullable | Ограничения и enum | Description |
| --- | --- | --- | --- | --- | --- |
| `company_name` | нет | `string` | нет | — | Название компании. |
| `inn` | нет | `string` | нет | — | ИНН. |
| `kpp` | нет | `string` | нет | — | КПП. |

### posting.v4.PostingFbsUnfulfilledListResponse.Postings.Optional

<a id="schema-posting-v4-postingfbsunfulfilledlistresponse-postings-optional"></a>

Список товаров с дополнительными характеристиками.

- Тип: `object`
- Nullable: **нет**
- Ограничения: —

#### Поля

| Поле | Required | Тип / вложенная ссылка | Nullable | Ограничения и enum | Description |
| --- | --- | --- | --- | --- | --- |
| `products_with_possible_mandatory_mark` | нет | array&lt;`string`&gt; | нет | — | Список товаров с возможной маркировкой. |

### posting.v4.PostingFbsUnfulfilledListResponse.Postings.Products

<a id="schema-posting-v4-postingfbsunfulfilledlistresponse-postings-products"></a>

- Тип: `object`
- Nullable: **нет**
- Ограничения: —

#### Поля

| Поле | Required | Тип / вложенная ссылка | Nullable | Ограничения и enum | Description |
| --- | --- | --- | --- | --- | --- |
| `imei` | нет | array&lt;`string`&gt; | нет | — | Список IMEI мобильных устройств. |
| `is_blr_traceable` | нет | `boolean` | нет | — | `true`, если товар отслеживаемый.<br> |
| `is_marketplace_buyout` | нет | `boolean` | нет | — | `true`, если Ozon выкупил товар.<br><br>[Подробнее о выкупе товаров в Базе знаний продавца](https://seller-edu.ozon.ru/commissions-tariffs/commissions-tariffs-ozon/prodaji-tovarov-v-eaes-i-drugie-strany#какие-товары-выкупает-ozon)<br> |
| `name` | нет | `string` | нет | — | Название товара. |
| `offer_id` | нет | `string` | нет | — | Идентификатор товара в системе продавца — артикул. |
| `price` | нет | [`money.postingMoney`](#schema-money-postingmoney) | нет | — | — |
| `product_color` | нет | `string` | нет | — | Цвет товара. |
| `quantity` | нет | `integer` | нет | format=`"int32"` | Количество товара в отправлении. |
| `sku` | нет | `integer` | нет | format=`"int64"` | Идентификатор товара в системе Ozon — SKU. |
| `weight` | нет | `number` | нет | format=`"double"` | Вес товара в упаковке. |

### posting.v4.PostingFbsUnfulfilledListResponse.Postings.Requirements

<a id="schema-posting-v4-postingfbsunfulfilledlistresponse-postings-requirements"></a>

Товары, для которых нужна дополнительная информация.<br><br>Чтобы перевести отправление в следующий статус, передайте:<br>- страну-изготовителя; <br>- номер грузовой таможенной декларации (ГТД);<br>- регистрационный номер партии товара (РНПТ);<br>- маркировку «Честный знак»;<br>- другие маркировки;<br>- вес.<br>

- Тип: `object`
- Nullable: **нет**
- Ограничения: —

#### Поля

| Поле | Required | Тип / вложенная ссылка | Nullable | Ограничения и enum | Description |
| --- | --- | --- | --- | --- | --- |
| `products_requiring_change_country` | нет | array&lt;`string`&gt; | нет | — | Список идентификаторов товаров (SKU), для которых нужно изменить страну-изготовителя. Чтобы изменить страну-изготовителя, используйте методы [/v2/posting/fbs/product/country/list](#operation/PostingAPI_ListCountryProductFbsPostingV2) и [/v2/posting/fbs/product/country/set](#operation/PostingAPI_SetCountryProductFbsPostingV2). |
| `products_requiring_country` | нет | array&lt;`string`&gt; | нет | — | Список идентификаторов товаров (SKU), для которых нужно передать информацию о стране-изготовителе.<br><br>Для сборки отправления передайте информацию о стране-изготовителе для всех перечисленных товаров методом [/v2/posting/fbs/product/country/set](#operation/PostingAPI_SetCountryProductFbsPostingV2).<br> |
| `products_requiring_gtd` | нет | array&lt;`string`&gt; | нет | — | Список идентификаторов товаров (SKU), для которых нужно передать номера грузовой таможенной декларации (ГТД).<br><br>До сборки отправления передайте для всех перечисленных товаров номер грузовой таможенной декларации или информацию о том, <br>что номера нет, методом [/v6/fbs/posting/product/exemplar/set](#operation/PostingAPI_FbsPostingProductExemplarSetV6).<br> |
| `products_requiring_imei` | нет | array&lt;`string`&gt; | нет | — | Список идентификаторов товаров, для которых нужно передать IMEI. |
| `products_requiring_jw_uin` | нет | array&lt;`string`&gt; | нет | — | Список товаров, для которых нужно передать уникальный идентификационный номер (УИН) ювелирного изделия.<br><br>До сборки отправления передайте для всех перечисленных товаров УИН методом [/v6/fbs/posting/product/exemplar/set](#operation/PostingAPI_FbsPostingProductExemplarSetV6).<br> |
| `products_requiring_mandatory_mark` | нет | array&lt;`string`&gt; | нет | — | Список идентификаторов товаров (SKU), для которых нужно передать маркировку «Честный знак».<br><br>До сборки отправления передайте для всех перечисленных товаров маркировку «Честный знак» методом [/v6/fbs/posting/product/exemplar/set](#operation/PostingAPI_FbsPostingProductExemplarSetV6).<br> |
| `products_requiring_rnpt` | нет | array&lt;`string`&gt; | нет | — | Список идентификаторов товаров (SKU), для которых нужно передать регистрационный номер партии товара (РНПТ).<br><br>До сборки отправления передайте для всех перечисленных товаров РНПТ методом [/v6/fbs/posting/product/exemplar/set](#operation/PostingAPI_FbsPostingProductExemplarSetV6).<br> |
| `products_requiring_weight` | нет | array&lt;`string`&gt; | нет | — | Список товаров, для которых нужно передать вес. |

### posting.v4.PostingFbsUnfulfilledListResponse.Postings.SortingCenter

<a id="schema-posting-v4-postingfbsunfulfilledlistresponse-postings-sortingcenter"></a>

Информация о сортировочном центре, в который нужно привезти отправление. Для `integration_type_flow = hybrid_3pl_tracking`.<br>Если значение `null`, информацию получить не удалось.<br>

- Тип: `object`
- Nullable: **нет**
- Ограничения: —

#### Поля

| Поле | Required | Тип / вложенная ссылка | Nullable | Ограничения и enum | Description |
| --- | --- | --- | --- | --- | --- |
| `code` | нет | `string` | нет | — | Код сортировочного центра. |
| `name` | нет | `string` | нет | — | Название сортировочного центра. |

### posting.v4.PostingFbsUnfulfilledListResponse.Postings.Tariffication

<a id="schema-posting-v4-postingfbsunfulfilledlistresponse-postings-tariffication"></a>

Информация по тарификации отгрузки.

- Тип: `object`
- Nullable: **нет**
- Ограничения: —

#### Поля

| Поле | Required | Тип / вложенная ссылка | Nullable | Ограничения и enum | Description |
| --- | --- | --- | --- | --- | --- |
| `current_tariff_charge` | нет | [`money.Money.Current_tariff_charge`](#schema-money-money-current-tariff-charge) | нет | — | — |
| `current_tariff_min_charge` | нет | [`money.Money.Current_tariff_min_charge`](#schema-money-money-current-tariff-min-charge) | нет | — | — |
| `current_tariff_rate` | нет | `number` | нет | format=`"double"` | Процент тарификации. |
| `current_tariff_type` | нет | `string` | нет | — | Тип тарификации — скидка или надбавка. |
| `next_tariff_charge` | нет | [`money.Money.Next_tariff_charge`](#schema-money-money-next-tariff-charge) | нет | — | — |
| `next_tariff_min_charge` | нет | [`money.Money.Next_tariff_min_charge`](#schema-money-money-next-tariff-min-charge) | нет | — | — |
| `next_tariff_rate` | нет | `number` | нет | format=`"double"` | Процент, по которому будет тарифицироваться отправление через время из параметра `next_tariff_starts_at`. |
| `next_tariff_starts_at` | нет | `string` | нет | format=`"date-time"`; pattern=`" YYYY-MM-DDThh:mm:ss.mcsZ"` | Дата и время, когда начнёт применяться новый тариф. |
| `next_tariff_type` | нет | `string` | нет | — | Тип тарификации через время из параметра `next_tariff_starts_at` — скидка или надбавка. |

### posting.v4.PostingFbsUnfulfilledListResponse.Postings.TarifficationStep

<a id="schema-posting-v4-postingfbsunfulfilledlistresponse-postings-tarifficationstep"></a>

- Тип: `object`
- Nullable: **нет**
- Ограничения: —

#### Поля

| Поле | Required | Тип / вложенная ссылка | Nullable | Ограничения и enum | Description |
| --- | --- | --- | --- | --- | --- |
| `min_charge` | нет | [`money.Money.Current_tariff_min_charge`](#schema-money-money-current-tariff-min-charge) | нет | — | — |
| `tariff_charge` | нет | [`money.Money.Current_tariff_charge`](#schema-money-money-current-tariff-charge) | нет | — | — |
| `tariff_deadline_at` | нет | `string` | нет | format=`"date-time"` | Дата и время окончания этапа тарификации. После этой даты автоматически применяется следующий этап. |
| `tariff_rate` | нет | `number` | нет | format=`"double"` | Процент скидки или надбавки. |
| `tariff_type` | нет | `string` | нет | — | Тип тарификации. |

### postingBooleanResponse

<a id="schema-postingbooleanresponse"></a>

- Тип: `object`
- Nullable: **нет**
- Ограничения: —

#### Поля

| Поле | Required | Тип / вложенная ссылка | Nullable | Ограничения и enum | Description |
| --- | --- | --- | --- | --- | --- |
| `result` | нет | `boolean` | нет | — | Результат обработки запроса. `true`, если запрос выполнился без ошибок. |

### postingPostingFBSPackageLabelRequest

<a id="schema-postingpostingfbspackagelabelrequest"></a>

- Тип: `object`
- Nullable: **нет**
- Ограничения: —

#### Поля

| Поле | Required | Тип / вложенная ссылка | Nullable | Ограничения и enum | Description |
| --- | --- | --- | --- | --- | --- |
| `posting_number` | да | array&lt;`string`&gt; | нет | — | Идентификатор отправления. |

### postingPostingFBSPackageLabelResponse

<a id="schema-postingpostingfbspackagelabelresponse"></a>

- Тип: `object`
- Nullable: **нет**
- Ограничения: —

#### Поля

| Поле | Required | Тип / вложенная ссылка | Nullable | Ограничения и enum | Description |
| --- | --- | --- | --- | --- | --- |
| `file_content` | нет | `string` | нет | format=`"byte"` | Содержание файла в бинарном виде. |
| `file_name` | нет | `string` | нет | — | Название файла. |
| `content_type` | нет | `string` | нет | — | Тип файла. |

### postingv3FbsPostingWithParamsExamplars

<a id="schema-postingv3fbspostingwithparamsexamplars"></a>

Дополнительные поля, которые нужно добавить в ответ.

- Тип: `object`
- Nullable: **нет**
- Ограничения: —

#### Поля

| Поле | Required | Тип / вложенная ссылка | Nullable | Ограничения и enum | Description |
| --- | --- | --- | --- | --- | --- |
| `analytics_data` | нет | `boolean` | нет | — | Добавить в ответ данные аналитики. |
| `barcodes` | нет | `boolean` | нет | — | Добавить в ответ штрихкоды отправления. |
| `financial_data` | нет | `boolean` | нет | — | Добавить в ответ финансовые данные. |
| `legal_info` | нет | `boolean` | нет | — | Добавить в ответ юридическую информацию. |
| `product_exemplars` | нет | `boolean` | нет | — | Добавить в ответ данные о продуктах и их экземплярах. |
| `related_postings` | нет | `boolean` | нет | — | Добавить в ответ номера связанных отправлений. Связанные отправления — те, на которое было разделено родительское отправление при сборке.<br> |
| `translit` | нет | `boolean` | нет | — | Выполнить транслитерацию возвращаемых значений. |

### postingv3GetFbsPostingRequest

<a id="schema-postingv3getfbspostingrequest"></a>

- Тип: `object`
- Nullable: **нет**
- Ограничения: —

#### Поля

| Поле | Required | Тип / вложенная ссылка | Nullable | Ограничения и enum | Description |
| --- | --- | --- | --- | --- | --- |
| `posting_number` | да | `string` | нет | — | Идентификатор отправления. |
| `with` | нет | [`postingv3FbsPostingWithParamsExamplars`](#schema-postingv3fbspostingwithparamsexamplars) | нет | — | — |

### postingv3PostingMultiBoxQtySetV3Request

<a id="schema-postingv3postingmultiboxqtysetv3request"></a>

- Тип: `object`
- Nullable: **нет**
- Ограничения: —

#### Поля

| Поле | Required | Тип / вложенная ссылка | Nullable | Ограничения и enum | Description |
| --- | --- | --- | --- | --- | --- |
| `posting_number` | да | `string` | нет | — | Идентификатор многокоробочного отправления. |
| `multi_box_qty` | да | `integer` | нет | format=`"int64"` | Количество коробок, в которые упакован товар. |

### postingv3PostingMultiBoxQtySetV3Response

<a id="schema-postingv3postingmultiboxqtysetv3response"></a>

- Тип: `object`
- Nullable: **нет**
- Ограничения: —

#### Поля

| Поле | Required | Тип / вложенная ссылка | Nullable | Ограничения и enum | Description |
| --- | --- | --- | --- | --- | --- |
| `result` | нет | [`postingv3PostingMultiBoxQtySetV3ResponseResult`](#schema-postingv3postingmultiboxqtysetv3responseresult) | нет | — | — |

### postingv3PostingMultiBoxQtySetV3ResponseResult

<a id="schema-postingv3postingmultiboxqtysetv3responseresult"></a>

Результат передачи количества коробок.

- Тип: `object`
- Nullable: **нет**
- Ограничения: —

#### Поля

| Поле | Required | Тип / вложенная ссылка | Nullable | Ограничения и enum | Description |
| --- | --- | --- | --- | --- | --- |
| `result` | нет | `boolean` | нет | — | Возможные значения:<br>- `true` — значение передано успешно.<br>- `false` — при передаче произошла ошибка. Попробуйте снова.<br> |

### protobufAny

<a id="schema-protobufany"></a>

- Тип: `object`
- Nullable: **нет**
- Ограничения: —

#### Поля

| Поле | Required | Тип / вложенная ссылка | Nullable | Ограничения и enum | Description |
| --- | --- | --- | --- | --- | --- |
| `typeUrl` | нет | `string` | нет | — | Тип протокола передачи данных. |
| `value` | нет | `string` | нет | format=`"byte"` | Значение ошибки. |

### rpcStatus

<a id="schema-rpcstatus"></a>

- Тип: `object`
- Nullable: **нет**
- Ограничения: —

#### Поля

| Поле | Required | Тип / вложенная ссылка | Nullable | Ограничения и enum | Description |
| --- | --- | --- | --- | --- | --- |
| `code` | нет | `integer` | нет | format=`"int32"` | Код ошибки. |
| `details` | нет | array&lt;[`protobufAny`](#schema-protobufany)&gt; | нет | — | Дополнительная информация об ошибке. |
| `message` | нет | `string` | нет | — | Описание ошибки. |

### v1CarriageApproveRequest

<a id="schema-v1carriageapproverequest"></a>

- Тип: `object`
- Nullable: **нет**
- Ограничения: —

#### Поля

| Поле | Required | Тип / вложенная ссылка | Nullable | Ограничения и enum | Description |
| --- | --- | --- | --- | --- | --- |
| `carriage_id` | да | `integer` | нет | format=`"int64"` | Идентификатор отгрузки. |
| `containers_count` | нет | `integer` | нет | format=`"int32"` | Количество грузовых мест. <br><br>Используйте параметр, если вы подключены к доверительной приёмке и отгружаете заказы грузовыми местами. Если вы не подключены к доверительной приёмке, пропустите его.<br> |

### v1CarriageApproveResponse

<a id="schema-v1carriageapproveresponse"></a>

- Тип: `object`
- Nullable: **нет**
- Ограничения: —

#### Поля

| Поле | Required | Тип / вложенная ссылка | Nullable | Ограничения и enum | Description |
| --- | --- | --- | --- | --- | --- |
| — | — | — | — | — | — |

### v1CarriageCreateRequest

<a id="schema-v1carriagecreaterequest"></a>

- Тип: `object`
- Nullable: **нет**
- Ограничения: —

#### Поля

| Поле | Required | Тип / вложенная ссылка | Nullable | Ограничения и enum | Description |
| --- | --- | --- | --- | --- | --- |
| `all_blr_traceable` | нет | `boolean` | нет | — | `true`, если нужно создать отгрузку с прослеживаемыми товарами.<br> |
| `delivery_method_id` | нет | `integer` | нет | format=`"int64"` | Идентификатор метода доставки. |
| `departure_date` | нет | `string` | нет | format=`"date-time"` | Дата отгрузки. По умолчанию — текущая дата. |

### v1CarriageCreateResponse

<a id="schema-v1carriagecreateresponse"></a>

- Тип: `object`
- Nullable: **нет**
- Ограничения: —

#### Поля

| Поле | Required | Тип / вложенная ссылка | Nullable | Ограничения и enum | Description |
| --- | --- | --- | --- | --- | --- |
| `carriage_id` | нет | `integer` | нет | format=`"int64"` | Идентификатор перевозки. |

### v1CreateLabelBatchRequest

<a id="schema-v1createlabelbatchrequest"></a>

- Тип: `object`
- Nullable: **нет**
- Ограничения: —

#### Поля

| Поле | Required | Тип / вложенная ссылка | Nullable | Ограничения и enum | Description |
| --- | --- | --- | --- | --- | --- |
| `posting_number` | да | unspecified | нет | — | Номера отправлений, для которых нужны этикетки. |

### v1GetLabelBatchRequest

<a id="schema-v1getlabelbatchrequest"></a>

- Тип: `object`
- Nullable: **нет**
- Ограничения: —

#### Поля

| Поле | Required | Тип / вложенная ссылка | Nullable | Ограничения и enum | Description |
| --- | --- | --- | --- | --- | --- |
| `task_id` | да | `integer` | нет | format=`"int64"` | Номер задания на формирование этикеток из ответа метода [/v1/posting/fbs/package-label/create](#operation/PostingAPI_CreateLabelBatch). |

### v1GetLabelBatchResponse

<a id="schema-v1getlabelbatchresponse"></a>

- Тип: `object`
- Nullable: **нет**
- Ограничения: —

#### Поля

| Поле | Required | Тип / вложенная ссылка | Nullable | Ограничения и enum | Description |
| --- | --- | --- | --- | --- | --- |
| `result` | нет | [`v1GetLabelBatchResponseResult`](#schema-v1getlabelbatchresponseresult) | нет | — | — |

### v1GetLabelBatchResponseResult

<a id="schema-v1getlabelbatchresponseresult"></a>

Результат работы метода.

- Тип: `object`
- Nullable: **нет**
- Ограничения: —

#### Поля

| Поле | Required | Тип / вложенная ссылка | Nullable | Ограничения и enum | Description |
| --- | --- | --- | --- | --- | --- |
| `error` | нет | `string` | нет | — | Код ошибки. |
| `file_url` | нет | `string` | нет | — | Ссылка на файл с этикетками. |
| `printed_postings_count` | нет | `integer` | нет | format=`"int32"` | Количество напечатанных этикеток. |
| `status` | нет | `string` | нет | — | Статус формирования этикеток:<br>- `pending` — задание в очереди.<br>- `in_progress` — формируются.<br>- `completed` — файл с этикетками готов.<br>- `error` — ошибка при создании файла.<br> |
| `unprinted_postings` | нет | array&lt;[`ResultUnprintedPosting`](#schema-resultunprintedposting)&gt; | нет | — | Информация об ошибках, из-за которых не получилось напечатать этикетки. |
| `unprinted_postings_count` | нет | `integer` | нет | format=`"int32"` | Количество этикеток, которые не получилось напечатать. |

### v1GetRestrictionsRequest

<a id="schema-v1getrestrictionsrequest"></a>

- Тип: `object`
- Nullable: **нет**
- Ограничения: —

#### Поля

| Поле | Required | Тип / вложенная ссылка | Nullable | Ограничения и enum | Description |
| --- | --- | --- | --- | --- | --- |
| `posting_number` | да | `string` | нет | — | Номер отправления, для которого нужно определить ограничения. |

### v1GetRestrictionsResponse

<a id="schema-v1getrestrictionsresponse"></a>

- Тип: `object`
- Nullable: **нет**
- Ограничения: —

#### Поля

| Поле | Required | Тип / вложенная ссылка | Nullable | Ограничения и enum | Description |
| --- | --- | --- | --- | --- | --- |
| `result` | нет | [`v1Restriction`](#schema-v1restriction) | нет | — | — |

### v1Restriction

<a id="schema-v1restriction"></a>

- Тип: `object`
- Nullable: **нет**
- Ограничения: —

#### Поля

| Поле | Required | Тип / вложенная ссылка | Nullable | Ограничения и enum | Description |
| --- | --- | --- | --- | --- | --- |
| `posting_number` | нет | `string` | нет | — | Номер отправления. |
| `max_posting_weight` | нет | `number` | нет | format=`"double"` | Ограничение по максимальному весу в граммах. |
| `min_posting_weight` | нет | `number` | нет | format=`"double"` | Ограничение по минимальному весу в граммах. |
| `width` | нет | `number` | нет | format=`"double"` | Ограничение по ширине в сантиметрах. |
| `length` | нет | `number` | нет | format=`"double"` | Ограничение по длине в сантиметрах. |
| `height` | нет | `number` | нет | format=`"double"` | Ограничение по высоте в сантиметрах. |
| `max_posting_price` | нет | `number` | нет | format=`"double"` | Ограничение по максимальной стоимости отправления в рублях. |
| `min_posting_price` | нет | `number` | нет | format=`"double"` | Ограничение по минимальной стоимости отправления в рублях. |

### v1SetPostingsRequest

<a id="schema-v1setpostingsrequest"></a>

- Тип: `object`
- Nullable: **нет**
- Ограничения: —

#### Поля

| Поле | Required | Тип / вложенная ссылка | Nullable | Ограничения и enum | Description |
| --- | --- | --- | --- | --- | --- |
| `carriage_id` | да | `integer` | нет | format=`"int64"` | Идентификатор отгрузки. |
| `posting_numbers` | да | array&lt;`string`&gt; | нет | — | Актуальный список отправлений. |

### v1SetPostingsResponse

<a id="schema-v1setpostingsresponse"></a>

- Тип: `object`
- Nullable: **нет**
- Ограничения: —

#### Поля

| Поле | Required | Тип / вложенная ссылка | Nullable | Ограничения и enum | Description |
| --- | --- | --- | --- | --- | --- |
| `result` | нет | unspecified | нет | — | — |

### v2CreateLabelBatchResponse

<a id="schema-v2createlabelbatchresponse"></a>

- Тип: `object`
- Nullable: **нет**
- Ограничения: —

#### Поля

| Поле | Required | Тип / вложенная ссылка | Nullable | Ограничения и enum | Description |
| --- | --- | --- | --- | --- | --- |
| `result` | нет | [`v2CreateLabelBatchResponseResult`](#schema-v2createlabelbatchresponseresult) | нет | — | — |

### v2CreateLabelBatchResponseResult

<a id="schema-v2createlabelbatchresponseresult"></a>

Результат работы метода.

- Тип: `object`
- Nullable: **нет**
- Ограничения: —

#### Поля

| Поле | Required | Тип / вложенная ссылка | Nullable | Ограничения и enum | Description |
| --- | --- | --- | --- | --- | --- |
| `tasks` | нет | array&lt;[`v2CreateLabelBatchResponseResultTasks`](#schema-v2createlabelbatchresponseresulttasks)&gt; | нет | — | Список заданий. |

### v2CreateLabelBatchResponseResultTasks

<a id="schema-v2createlabelbatchresponseresulttasks"></a>

- Тип: `object`
- Nullable: **нет**
- Ограничения: —

#### Поля

| Поле | Required | Тип / вложенная ссылка | Nullable | Ограничения и enum | Description |
| --- | --- | --- | --- | --- | --- |
| `task_id` | нет | `integer` | нет | format=`"int64"` | Идентификатор задания на формирование этикеток. В зависимости от типа этикетки передайте значение в метод [/v1/posting/fbs/package-label/get](#operation/PostingAPI_GetLabelBatch). |
| `task_type` | нет | `string` | нет | — | Тип задания на формирование этикеток:<br>- `big_label` — для обычной этикетки,<br>- `small_label` — для маленькой этикетки.<br> |

### v2FboSinglePostingLegalInfo

<a id="schema-v2fbosinglepostinglegalinfo"></a>

Юридическая информация о покупателе.

- Тип: `object`
- Nullable: **нет**
- Ограничения: —

#### Поля

| Поле | Required | Тип / вложенная ссылка | Nullable | Ограничения и enum | Description |
| --- | --- | --- | --- | --- | --- |
| `company_name` | нет | `string` | нет | — | Название компании. |
| `inn` | нет | `string` | нет | — | ИНН. |
| `kpp` | нет | `string` | нет | — | КПП. |

### v2FbsPostingProductCountryListRequest

<a id="schema-v2fbspostingproductcountrylistrequest"></a>

- Тип: `object`
- Nullable: **нет**
- Ограничения: —

#### Поля

| Поле | Required | Тип / вложенная ссылка | Nullable | Ограничения и enum | Description |
| --- | --- | --- | --- | --- | --- |
| `name_search` | нет | `string` | нет | — | Фильтрация по строке. |

### v2FbsPostingProductCountryListResponse

<a id="schema-v2fbspostingproductcountrylistresponse"></a>

- Тип: `object`
- Nullable: **нет**
- Ограничения: —

#### Поля

| Поле | Required | Тип / вложенная ссылка | Nullable | Ограничения и enum | Description |
| --- | --- | --- | --- | --- | --- |
| `result` | нет | array&lt;[`v2FbsPostingProductCountryListResponseResult`](#schema-v2fbspostingproductcountrylistresponseresult)&gt; | нет | — | Список стран-изготовителей и ISO коды. |

### v2FbsPostingProductCountryListResponseResult

<a id="schema-v2fbspostingproductcountrylistresponseresult"></a>

- Тип: `object`
- Nullable: **нет**
- Ограничения: —

#### Поля

| Поле | Required | Тип / вложенная ссылка | Nullable | Ограничения и enum | Description |
| --- | --- | --- | --- | --- | --- |
| `name` | нет | `string` | нет | — | Название страны на русском языке. |
| `country_iso_code` | нет | `string` | нет | — | ISO код страны. |

### v2FbsPostingProductCountrySetRequest

<a id="schema-v2fbspostingproductcountrysetrequest"></a>

- Тип: `object`
- Nullable: **нет**
- Ограничения: —

#### Поля

| Поле | Required | Тип / вложенная ссылка | Nullable | Ограничения и enum | Description |
| --- | --- | --- | --- | --- | --- |
| `posting_number` | да | `string` | нет | — | Номер отправления. |
| `product_id` | да | `integer` | нет | format=`"int64"` | Идентификатор товара в системе Ozon — `product_id`. |
| `country_iso_code` | да | `string` | нет | — | Двухбуквенный код добавляемой страны по стандарту ISO_3166-1.<br><br>Список доступных стран-изготовителей и их ISO коды можно получить с помощью метода [/v2/posting/fbs/product/country/list](#operation/PostingAPI_ListCountryProductFbsPostingV2).<br> |

### v2FbsPostingProductCountrySetResponse

<a id="schema-v2fbspostingproductcountrysetresponse"></a>

- Тип: `object`
- Nullable: **нет**
- Ограничения: —

#### Поля

| Поле | Required | Тип / вложенная ссылка | Nullable | Ограничения и enum | Description |
| --- | --- | --- | --- | --- | --- |
| `product_id` | нет | `integer` | нет | format=`"int64"` | Идентификатор товара в системе Ozon — `product_id`. |
| `is_gtd_needed` | нет | `boolean` | нет | — | Признак того, что необходимо передать номер грузовой таможенной декларации (ГТД) для продукта и отправления. |

### v2MovePostingToAwaitingDeliveryRequest

<a id="schema-v2movepostingtoawaitingdeliveryrequest"></a>

- Тип: `object`
- Nullable: **нет**
- Ограничения: —

#### Поля

| Поле | Required | Тип / вложенная ссылка | Nullable | Ограничения и enum | Description |
| --- | --- | --- | --- | --- | --- |
| `posting_number` | да | array&lt;`string`&gt; | нет | — | Идентификатор отправления. Максимальное количество в одном запросе — 100. |

### v2PostingFBSGetBarcodeRequest

<a id="schema-v2postingfbsgetbarcoderequest"></a>

- Тип: `object`
- Nullable: **нет**
- Ограничения: —

#### Поля

| Поле | Required | Тип / вложенная ссылка | Nullable | Ограничения и enum | Description |
| --- | --- | --- | --- | --- | --- |
| `id` | да | `integer` | нет | format=`"int64"` | Идентификатор перевозки. |

### v2PostingFBSGetBarcodeResponse

<a id="schema-v2postingfbsgetbarcoderesponse"></a>

- Тип: `object`
- Nullable: **нет**
- Ограничения: —

#### Поля

| Поле | Required | Тип / вложенная ссылка | Nullable | Ограничения и enum | Description |
| --- | --- | --- | --- | --- | --- |
| `file_content` | нет | `string` | нет | — | Изображение со штрихкодом в бинарном виде. |
| `file_name` | нет | `string` | нет | — | Название файла. |
| `content_type` | нет | `string` | нет | — | Тип файла. |

### v2PostingFBSGetBarcodeTextResponse

<a id="schema-v2postingfbsgetbarcodetextresponse"></a>

- Тип: `object`
- Nullable: **нет**
- Ограничения: —

#### Поля

| Поле | Required | Тип / вложенная ссылка | Nullable | Ограничения и enum | Description |
| --- | --- | --- | --- | --- | --- |
| `result` | нет | `string` | нет | — | Штрихкод в текстовом виде. |

### v2PostingFBSGetDigitalActRequest

<a id="schema-v2postingfbsgetdigitalactrequest"></a>

- Тип: `object`
- Nullable: **нет**
- Ограничения: —

#### Поля

| Поле | Required | Тип / вложенная ссылка | Nullable | Ограничения и enum | Description |
| --- | --- | --- | --- | --- | --- |
| `id` | да | `integer` | нет | format=`"int64"` | Номер задания на формирование документов (также идентификатор перевозки) из метода [POST /v2/posting/fbs/act/create](#operation/PostingAPI_PostingFBSActCreate). |
| `doc_type` | нет | unspecified | нет | format=`"string"` | Тип электронного документа:<br>- `act_of_acceptance` — лист отгрузки,<br>- `act_of_mismatch` — акт о расхождениях,<br>- `act_of_excess` — акт об излишках,<br>- `waybill` — транспортная накладная.<br> |

### v2PostingFBSGetDigitalActResponse

<a id="schema-v2postingfbsgetdigitalactresponse"></a>

- Тип: `object`
- Nullable: **нет**
- Ограничения: —

#### Поля

| Поле | Required | Тип / вложенная ссылка | Nullable | Ограничения и enum | Description |
| --- | --- | --- | --- | --- | --- |
| `file_content` | нет | `string` | нет | format=`"byte"` | Содержание файла в бинарном виде. |
| `file_name` | нет | `string` | нет | — | Название файла. |
| `content_type` | нет | `string` | нет | — | Тип файла. |

### v3AdditionalDataItem

<a id="schema-v3additionaldataitem"></a>

- Тип: `object`
- Nullable: **нет**
- Ограничения: —

#### Поля

| Поле | Required | Тип / вложенная ссылка | Nullable | Ограничения и enum | Description |
| --- | --- | --- | --- | --- | --- |
| `key` | нет | `string` | нет | — | — |
| `value` | нет | `string` | нет | — | — |

### v3Address

<a id="schema-v3address"></a>

Информация об адресе доставки.

- Тип: `object`
- Nullable: **нет**
- Ограничения: —

#### Поля

| Поле | Required | Тип / вложенная ссылка | Nullable | Ограничения и enum | Description |
| --- | --- | --- | --- | --- | --- |
| `address_tail` | нет | `string` | нет | — | Адрес в текстовом формате. |
| `city` | нет | `string` | нет | — | Город доставки. |
| `comment` | нет | `string` | нет | — | Комментарий к заказу. |
| `country` | нет | `string` | нет | — | Страна доставки. |
| `district` | нет | `string` | нет | — | Район доставки. |
| `latitude` | нет | `number` | нет | format=`"double"` | Широта. |
| `longitude` | нет | `number` | нет | format=`"double"` | Долгота. |
| `provider_pvz_code` | нет | `string` | нет | — | Код пункта выдачи заказов 3PL провайдера. |
| `pvz_code` | нет | `integer` | нет | format=`"int64"` | Код пункта выдачи заказов. |
| `region` | нет | `string` | нет | — | Регион доставки. |
| `zip_code` | нет | `string` | нет | — | Почтовый индекс получателя. |

### v3Addressee

<a id="schema-v3addressee"></a>

Контактные данные получателя.

- Тип: unspecified
- Nullable: **нет**
- Ограничения: —

#### Поля

| Поле | Required | Тип / вложенная ссылка | Nullable | Ограничения и enum | Description |
| --- | --- | --- | --- | --- | --- |
| `name` | нет | `string` | нет | — | Имя покупателя. |
| `phone` | нет | `string` | нет | pattern=`" +7(XXX)XXX-XX-XX"` | Подменный контактный телефон получателя. <br><br>[Подробнее о подменных номерах в Базе знаний](https://seller-edu.ozon.ru/rfbs/orders-cancellations/replacement-number)<br> |
| `pin` | нет | `string` | нет | — | Добавочный номер телефона получателя, вводится в тональном режиме. Только для отправлений realFBS со службами доставки:<br>  - `3pl_tracking` — доставка внешней службой, продавец регистрирует заказ.<br>  - `non_integrated` — доставка силами продавца.<br> |

### v3Barcodes

<a id="schema-v3barcodes"></a>

Штрихкоды отправления.

- Тип: `object`
- Nullable: **нет**
- Ограничения: —

#### Поля

| Поле | Required | Тип / вложенная ссылка | Nullable | Ограничения и enum | Description |
| --- | --- | --- | --- | --- | --- |
| `lower_barcode` | нет | `string` | нет | — | Нижний штрихкод на маркировке отправления. |
| `upper_barcode` | нет | `string` | нет | — | Верхний штрихкод на маркировке отправления. |

### v3Cancellation

<a id="schema-v3cancellation"></a>

Информация об отмене.

- Тип: `object`
- Nullable: **нет**
- Ограничения: —

#### Поля

| Поле | Required | Тип / вложенная ссылка | Nullable | Ограничения и enum | Description |
| --- | --- | --- | --- | --- | --- |
| `affect_cancellation_rating` | нет | `boolean` | нет | — | Если отмена влияет на рейтинг продавца — `true`. |
| `cancel_reason` | нет | `string` | нет | — | Причина отмены. |
| `cancel_reason_id` | нет | `integer` | нет | format=`"int64"` | Идентификатор причины отмены отправления. |
| `cancellation_initiator` | нет | `string` | нет | — | Инициатор отмены:<br>- `Продавец`, <br>- `Клиент` или `покупатель`,<br>- `Ozon`,  <br>- `Система`, <br>- `Служба доставки`.<br> |
| `cancellation_type` | нет | `string` | нет | — | Тип отмены отправления:<br>- `seller` — отменено продавцом;<br>- `client` или `customer` — отменено покупателем;<br>- `ozon` — отменено Ozon;<br>- `system`— отменено системой;<br>- `delivery` — отменено службой доставки.<br> |
| `cancelled_after_ship` | нет | `boolean` | нет | — | Если отмена произошла после сборки отправления — `true`. |

### v3Customer

<a id="schema-v3customer"></a>

Данные о покупателе.

- Тип: `object`
- Nullable: **нет**
- Ограничения: —

#### Поля

| Поле | Required | Тип / вложенная ссылка | Nullable | Ограничения и enum | Description |
| --- | --- | --- | --- | --- | --- |
| `address` | нет | [`v3Address`](#schema-v3address) | нет | — | — |
| `customer_id` | нет | `integer` | нет | format=`"int64"` | Идентификатор покупателя. |
| `name` | нет | `string` | нет | — | Имя покупателя. |
| `phone` | нет | `string` | нет | — | Подменный контактный телефон покупателя. <br><br>[Подробнее о подменных номерах в Базе знаний](https://seller-edu.ozon.ru/rfbs/orders-cancellations/replacement-number)<br> |

### v3DeliveryMethod

<a id="schema-v3deliverymethod"></a>

Метод доставки.

- Тип: `object`
- Nullable: **нет**
- Ограничения: —

#### Поля

| Поле | Required | Тип / вложенная ссылка | Nullable | Ограничения и enum | Description |
| --- | --- | --- | --- | --- | --- |
| `id` | нет | `integer` | нет | format=`"int64"` | Идентификатор способа доставки. |
| `name` | нет | `string` | нет | — | Название способа доставки. |
| `tpl_provider` | нет | `string` | нет | — | Служба доставки. |
| `tpl_provider_id` | нет | `integer` | нет | format=`"int64"` | Идентификатор службы доставки. |
| `warehouse` | нет | `string` | нет | — | Название склада. |
| `warehouse_id` | нет | `integer` | нет | format=`"int64"` | Идентификатор склада. |

### v3Dimensions

<a id="schema-v3dimensions"></a>

Размеры товара.

- Тип: `object`
- Nullable: **нет**
- Ограничения: —

#### Поля

| Поле | Required | Тип / вложенная ссылка | Nullable | Ограничения и enum | Description |
| --- | --- | --- | --- | --- | --- |
| `height` | нет | `string` | нет | — | Высота упаковки. |
| `length` | нет | `string` | нет | — | Длина товара. |
| `weight` | нет | `string` | нет | — | Вес товара в упаковке. |
| `width` | нет | `string` | нет | — | Ширина упаковки. |

### v3FbsPostingAnalyticsData

<a id="schema-v3fbspostinganalyticsdata"></a>

Данные аналитики.

- Тип: `object`
- Nullable: **нет**
- Ограничения: —

#### Поля

| Поле | Required | Тип / вложенная ссылка | Nullable | Ограничения и enum | Description |
| --- | --- | --- | --- | --- | --- |
| `city` | нет | `string` | нет | — | Город доставки. Только для отправлений rFBS и продавцов из СНГ. |
| `delivery_date_begin` | нет | `string` | нет | format=`"date-time"` | Дата и время начала доставки. |
| `delivery_date_end` | нет | `string` | нет | format=`"date-time"` | Дата и время конца доставки. |
| `delivery_type` | нет | `string` | нет | — | Способ доставки. |
| `is_legal` | нет | `boolean` | нет | — | Признак, что получатель юридическое лицо:<br>  - `true` — юридическое лицо,<br>  - `false` — физическое лицо.<br> |
| `is_premium` | нет | `boolean` | нет | — | Наличие подписки Premium. |
| `payment_type_group_name` | нет | `string` | нет | — | Способ оплаты: <br>- `картой онлайн`,<br>- `карта Ozon Банка`,<br>- `автосписание с карты Ozon Банка при выдаче`,<br>- `сохранённой картой при получении`,<br>- `Система Быстрых Платежей`, <br>- `Ozon Рассрочка`, <br>- `оплата на расчётный счёт`,<br>- `SberPay`,<br>- `предоплата на стороне внешнего продавца`.<br> |
| `region` | нет | `string` | нет | — | Регион доставки. Только для отправлений rFBS. |
| `tpl_provider` | нет | `string` | нет | — | Служба доставки. |
| `tpl_provider_id` | нет | `integer` | нет | format=`"int64"` | Идентификатор службы доставки. |
| `warehouse` | нет | `string` | нет | — | Название склада отправки заказа. |
| `warehouse_id` | нет | `integer` | нет | format=`"int64"` | Идентификатор склада. |
| `client_delivery_date_begin` | нет | `string` | нет | format=`"date-time"` | Дата и время начала доставки. Только для отправлений, оформленных через [Ozon Доставку](#tag/OzonLogistics). |
| `client_delivery_date_end` | нет | `string` | нет | format=`"date-time"` | Ожидаемая дата, до которой заказ будет доставлен. Только для отправлений, оформленных через [Ozon Доставку](#tag/OzonLogistics). |

### v3FbsPostingDetail

<a id="schema-v3fbspostingdetail"></a>

Информация об отправлении.

- Тип: `object`
- Nullable: **нет**
- Ограничения: —

#### Поля

| Поле | Required | Тип / вложенная ссылка | Nullable | Ограничения и enum | Description |
| --- | --- | --- | --- | --- | --- |
| `additional_data` | нет | array&lt;[`v3AdditionalDataItem`](#schema-v3additionaldataitem)&gt; | нет | — | — |
| `addressee` | нет | [`v3Addressee`](#schema-v3addressee) | нет | — | — |
| `analytics_data` | нет | [`v3FbsPostingAnalyticsData`](#schema-v3fbspostinganalyticsdata) | нет | — | — |
| `available_actions` | нет | unspecified | нет | — | Доступные действия и информация об отправлении:<br>- `arbitration` — открыть спор;<br>- `awaiting_delivery` — перевести в статус «Ожидает отгрузки»;<br>- `can_create_chat` — начать чат с покупателем;<br>- `cancel` — отменить отправление;<br>- `click_track_number` — просмотреть по трек-номеру историю изменения статусов в личном кабинете;<br>- `customer_phone_available` — телефон покупателя;<br>- `has_weight_products` — весовые товары в отправлении;<br>- `hide_region_and_city` — скрыть регион и город покупателя в отчёте;<br>- `invoice_get` —  получить информацию из счёта-фактуры;<br>- `invoice_send` — создать счёт-фактуру;<br>- `invoice_update` — отредактировать счёт-фактуру;<br>- `label_download_big` — скачать большую этикетку;<br>- `label_download_small` — скачать маленькую этикетку;<br>- `label_download` — скачать этикетку;<br>- `non_int_delivered` — перевести в статус «Условно доставлен»;<br>- `non_int_delivering` — перевести в статус «Доставляется»;<br>- `non_int_last_mile` — перевести в статус «Курьер в пути»;<br>- `product_cancel` — отменить часть товаров в отправлении;<br>- `set_cutoff` — необходимо указать дату отгрузки, воспользуйтесь методом [/v1/posting/cutoff/set](#operation/PostingAPI_SetPostingCutoff);<br>- `set_timeslot` — изменить время доставки покупателю;<br>- `set_track_number` — указать или изменить трек-номер;<br>- `ship_async_in_process` — отправление собирается;<br>- `ship_async_retry` — собрать отправление повторно после ошибки сборки;<br>- `ship_async` — собрать отправление;<br>- `ship_with_additional_info` — необходимо заполнить дополнительную информацию;<br>- `ship` — собрать отправление;<br>- `update_cis` — изменить дополнительную информацию.<br> |
| `barcodes` | нет | [`v3Barcodes`](#schema-v3barcodes) | нет | — | — |
| `cancellation` | нет | [`v3Cancellation`](#schema-v3cancellation) | нет | — | — |
| `courier` | нет | [`FbsPostingDetailCourier`](#schema-fbspostingdetailcourier) | нет | — | — |
| `customer` | нет | [`v3Customer`](#schema-v3customer) | нет | — | — |
| `container` | нет | [`posting.v4.PostingFbsListResponse.Postings.Container`](#schema-posting-v4-postingfbslistresponse-postings-container) | нет | — | — |
| `container_sort_type` | нет | `string` | нет | — | Тип сортировки грузоместа:<br>  - `SORT` — сортируемый;<br>  - `NON-SORT` — несортируемый.<br> |
| `delivering_date` | нет | `string` | нет | format=`"date-time"` | Дата передачи отправления в доставку. |
| `delivery_method` | нет | [`v3DeliveryMethod`](#schema-v3deliverymethod) | нет | — | — |
| `delivery_price` | нет | `string` | нет | — | Стоимость доставки. |
| `external_order` | нет | [`posting.v3.FbsPostingDetail.ExternalOrder`](#schema-posting-v3-fbspostingdetail-externalorder) | нет | — | — |
| `fact_delivery_date` | нет | `string` | нет | format=`"date-time"` | Дата фактической передачи отправления в доставку. |
| `financial_data` | нет | [`v3PostingFinancialData`](#schema-v3postingfinancialdata) | нет | — | — |
| `in_process_at` | нет | `string` | нет | format=`"date-time"` | Дата и время начала обработки отправления. |
| `integration_type_flow` | нет | `string` | нет | — | Процесс обработки отправления:<br>- `ozon` — доставка силами Ozon;<br>- `aggregator` — доставка внешней службой, Ozon регистрирует заказ;<br>- `non_integrated` — доставка силами продавца;<br>- `3pl_tracking` — доставка внешней службой, продавец регистрирует заказ;<br>- `hybrid` — гибридная интеграция;<br>- `hybrid_aggregator` — гибридная интеграция с доставкой внешней службой, Ozon регистрирует заказ;<br>- `hybrid_non_integrated` — гибридная интеграция с доставкой силами продавца;<br>- `hybrid_3pl_tracking` — гибридная интеграция с доставкой внешней службой, продавец регистрирует заказ;<br>- `click_and_collect` — бронирование в магазине партнёра;<br>- `FBP` — доставка с партнёрских складов Ozon.<br> |
| `is_express` | нет | `boolean` | нет | — | Если использовалась быстрая доставка Ozon Express — `true`. |
| `is_multibox` | нет | `boolean` | нет | — | Признак, что в отправлении есть многокоробочный товар и нужно передать количество коробок для него:<br><br>- `true` — до сборки передайте количество коробок через метод [/v3/posting/multiboxqty/set](#operation/PostingAPI_PostingMultiBoxQtySetV3).<br>- `false` — отправление собрано с указанием количества коробок в параметре `multi_box_qty` или в отправлении нет многокоробочного товара.<br> |
| `legal_info` | нет | [`v2FboSinglePostingLegalInfo`](#schema-v2fbosinglepostinglegalinfo) | нет | — | — |
| `multi_box_qty` | нет | `integer` | нет | format=`"int32"` | Количество коробок, в которые упакован товар. |
| `optional` | нет | [`v3FbsPostingDetailOptional`](#schema-v3fbspostingdetailoptional) | нет | — | — |
| `order_id` | нет | `integer` | нет | format=`"int64"` | Идентификатор заказа, к которому относится отправление. |
| `order_number` | нет | `string` | нет | — | Номер заказа, к которому относится отправление. |
| `parent_posting_number` | нет | `string` | нет | — | Номер родительского отправления, в результате разделения которого появилось текущее. |
| `pickup_code_verified_at` | нет | `string` | нет | format=`"date-time"` | Дата и время успешной валидации кода курьера. Чтобы проверить код курьера, воспользуйтесь методом [/v1/posting/fbs/pick-up-code/verify](#operation/PostingAPI_PostingFBSPickupCodeVerify). |
| `posting_number` | нет | `string` | нет | — | Номер отправления. |
| `product_exemplars` | нет | [`v3FbsPostingProductExemplarsV3`](#schema-v3fbspostingproductexemplarsv3) | нет | — | — |
| `products` | нет | array&lt;[`v3PostingProductDetail`](#schema-v3postingproductdetail)&gt; | нет | — | Массив товаров в отправлении. |
| `provider_status` | нет | `string` | нет | — | Статус службы доставки. |
| `prr_option` | нет | [`FbsPostingDetailPrrOption`](#schema-fbspostingdetailprroption) | нет | — | — |
| `related_postings` | нет | [`v3FbsPostingDetailRelatedPostings`](#schema-v3fbspostingdetailrelatedpostings) | нет | — | — |
| `related_weight_postings` | нет | array&lt;`string`&gt; | нет | — | Список номеров связанных весовых отправлений. |
| `require_blr_traceable_attrs` | нет | `boolean` | нет | — | `true`, если нужно заполнить атрибуты прослеживаемости.<br> |
| `requirements` | нет | [`v3FbsPostingRequirementsV3`](#schema-v3fbspostingrequirementsv3) | нет | — | — |
| `shipment_date` | нет | `string` | нет | format=`"date-time"` | Дата и время, до которой необходимо собрать отправление. Показываем рекомендованное время отгрузки. По истечении этого времени начнёт применяться новый тариф, информацию о нём уточняйте в поле `tariffication`. |
| `shipment_date_without_delay` | нет | `string` | нет | format=`"date-time"` | Дата и время отгрузки без просрочки. |
| `sorting_center` | нет | [`posting.v3.FbsPostingDetail.SortingCenter`](#schema-posting-v3-fbspostingdetail-sortingcenter) | нет | — | — |
| `status` | нет | `string` | нет | — | Статус отправления:<br>- `acceptance_in_progress` — идёт приёмка,<br>- `arbitration` — арбитраж,<br>- `awaiting_approve` — ожидает подтверждения,<br>- `awaiting_deliver` — ожидает отгрузки,<br>- `awaiting_packaging` — ожидает упаковки,<br>- `awaiting_registration` — ожидает регистрации,<br>- `awaiting_verification` — создано,<br>- `cancelled` — отменено,<br>- `cancelled_from_split_pending` — отменён из-за разделения отправления,<br>- `client_arbitration` — клиентский арбитраж доставки,<br>- `delivered` — доставлено,<br>- `delivering` — доставляется,<br>- `driver_pickup` — у водителя,<br>- `not_accepted` — не принят на сортировочном центре,<br> |
| `substatus` | нет | `string` | нет | — | Подстатус отправления:<br>- `posting_acceptance_in_progress` — идёт приёмка,<br>- `posting_in_arbitration` — арбитраж,<br>- `posting_created` — создано,<br>- `posting_in_carriage` — в перевозке,<br>- `posting_not_in_carriage` — не добавлено в перевозку,<br>- `posting_registered` — зарегистрировано,<br>- `posting_transferring_to_delivery` (`status=awaiting_deliver`) — передаётся в доставку,<br>- `posting_awaiting_passport_data` — ожидает паспортных данных, <br>- `posting_created` — создано,<br>- `posting_awaiting_registration` — ожидает регистрации,<br>- `posting_registration_error` — ошибка регистрации,<br>- `posting_transferring_to_delivery` (`status=awaiting_registration`) — передаётся курьеру,<br>- `posting_split_pending` — создано,<br>- `posting_canceled` — отменено,<br>- `posting_in_client_arbitration` — клиентский арбитраж доставки,<br>- `posting_delivered` — доставлено,<br>- `posting_received` — получено,<br>- `posting_conditionally_delivered` — условно доставлено,<br>- `posting_in_courier_service` — курьер в пути,<br>- `posting_in_pickup_point` — в пункте выдачи,<br>- `posting_on_way_to_city` — в пути в ваш город,<br>- `posting_on_way_to_pickup_point` — в пути в пункт выдачи,<br>- `posting_returned_to_warehouse` — возвращено на склад,<br>- `posting_transferred_to_courier_service` — передаётся в службу доставки,<br>- `posting_driver_pick_up` — у водителя,<br>- `posting_not_in_sort_center` — не принято на сортировочном центре,<br>- `ship_failed` — сборка не удалась.<br> |
| `previous_substatus` | нет | `string` | нет | — | Предыдущий подстатус отправления. Возможные значения:<br>- `posting_acceptance_in_progress` — идёт приёмка,<br>- `posting_in_arbitration` — арбитраж,<br>- `posting_created` — создано,<br>- `posting_in_carriage` — в перевозке,<br>- `posting_not_in_carriage` — не добавлено в перевозку,<br>- `posting_registered` — зарегистрировано,<br>- `posting_transferring_to_delivery` (`status=awaiting_deliver`) — передаётся в доставку,<br>- `posting_awaiting_passport_data` — ожидает паспортных данных, <br>- `posting_created` — создано,<br>- `posting_awaiting_registration` — ожидает регистрации,<br>- `posting_registration_error` — ошибка регистрации,<br>- `posting_transferring_to_delivery` (`status=awaiting_registration`) — передаётся курьеру,<br>- `posting_split_pending` — создано,<br>- `posting_canceled` — отменено,<br>- `posting_in_client_arbitration` — клиентский арбитраж доставки,<br>- `posting_delivered` — доставлено,<br>- `posting_received` — получено,<br>- `posting_conditionally_delivered` — условно доставлено,<br>- `posting_in_courier_service` — курьер в пути,<br>- `posting_in_pickup_point` — в пункте выдачи,<br>- `posting_on_way_to_city` — в пути в ваш город,<br>- `posting_on_way_to_pickup_point` — в пути в пункт выдачи,<br>- `posting_returned_to_warehouse` — возвращено на склад,<br>- `posting_transferred_to_courier_service` — передаётся в службу доставки,<br>- `posting_driver_pick_up` — у водителя,<br>- `posting_not_in_sort_center` — не принято на сортировочном центре.<br> |
| `tpl_integration_type` | нет | `string` | нет | — | Тип интеграции со службой доставки:<br>  - `ozon` — доставка через Ozon логистику.<br>  - `aggregator` — доставка внешней службой, Ozon регистрирует заказ.<br>  - `3pl_tracking` — доставка внешней службой, продавец регистрирует заказ.<br>  - `non_integrated` — доставка силами продавца.<br> |
| `tracking_number` | нет | `string` | нет | — | Трек-номер отправления. |
| `tariffication` | нет | [`v3FbsTariffication`](#schema-v3fbstariffication) | нет | — | — |
| `tariffication_steps` | нет | array&lt;[`posting.v4.PostingFbsListResponse.Postings.TarifficationStep`](#schema-posting-v4-postingfbslistresponse-postings-tarifficationstep)&gt; | нет | — | Этапы тарификации. |

### v3FbsPostingDetailOptional

<a id="schema-v3fbspostingdetailoptional"></a>

Список товаров с дополнительными характеристиками.

- Тип: `object`
- Nullable: **нет**
- Ограничения: —

#### Поля

| Поле | Required | Тип / вложенная ссылка | Nullable | Ограничения и enum | Description |
| --- | --- | --- | --- | --- | --- |
| `products_with_possible_mandatory_mark` | нет | array&lt;`string`&gt; | нет | — | Список товаров с возможной маркировкой. |

### v3FbsPostingDetailRelatedPostings

<a id="schema-v3fbspostingdetailrelatedpostings"></a>

Связанные отправления.

- Тип: `object`
- Nullable: **нет**
- Ограничения: —

#### Поля

| Поле | Required | Тип / вложенная ссылка | Nullable | Ограничения и enum | Description |
| --- | --- | --- | --- | --- | --- |
| `related_posting_numbers` | нет | unspecified | нет | — | Список номеров связанных отправлений. |

### v3FbsPostingExemplarProductV3

<a id="schema-v3fbspostingexemplarproductv3"></a>

Список товаров и экземпляров.

- Тип: `object`
- Nullable: **нет**
- Ограничения: —

#### Поля

| Поле | Required | Тип / вложенная ссылка | Nullable | Ограничения и enum | Description |
| --- | --- | --- | --- | --- | --- |
| `exemplars` | нет | array&lt;[`v3FbsPostingProductExemplarInfoV3`](#schema-v3fbspostingproductexemplarinfov3)&gt; | нет | — | Информация по экземплярам. |
| `sku` | нет | `integer` | нет | format=`"int64"` | Идентификатор товара в системе Ozon — SKU. |

### v3FbsPostingProductExemplarInfoV3

<a id="schema-v3fbspostingproductexemplarinfov3"></a>

- Тип: `object`
- Nullable: **нет**
- Ограничения: —

#### Поля

| Поле | Required | Тип / вложенная ссылка | Nullable | Ограничения и enum | Description |
| --- | --- | --- | --- | --- | --- |
| `exemplar_id` | нет | `integer` | нет | format=`"int64"` | Идентификатор экземпляра. |
| `mandatory_mark` | нет | `string` | нет | — | Обязательная маркировка «Честный ЗНАК». |
| `gtd` | нет | `string` | нет | — | Номер грузовой таможенной декларации (ГТД). |
| `is_gtd_absent` | нет | `boolean` | нет | — | Признак того, что не указан номер таможенной декларации. |
| `rnpt` | нет | `string` | нет | — | Регистрационный номер партии товара (РНПТ). |
| `is_rnpt_absent` | нет | `boolean` | нет | — | Признак того, что не указан регистрационный номер партии товара (РНПТ). |
| `weight` | нет | `number` | нет | format=`"float"` | Фактический вес экземпляра. |
| `imei` | нет | array&lt;`string`&gt; | нет | — | Список IMEI мобильных устройств. |

### v3FbsPostingProductExemplarsV3

<a id="schema-v3fbspostingproductexemplarsv3"></a>

Информация по продуктам и их экземплярам.<br><br>Ответ содержит поле `product_exemplars`, если в запросе передан признак `with.product_exemplars = true`.<br>

- Тип: `object`
- Nullable: **нет**
- Ограничения: —

#### Поля

| Поле | Required | Тип / вложенная ссылка | Nullable | Ограничения и enum | Description |
| --- | --- | --- | --- | --- | --- |
| `products` | нет | array&lt;[`v3FbsPostingExemplarProductV3`](#schema-v3fbspostingexemplarproductv3)&gt; | нет | — | Информация по продуктам. |

### v3FbsPostingRequirementsV3

<a id="schema-v3fbspostingrequirementsv3"></a>

Cписок продуктов, для которых нужно передать страну-изготовителя, номер грузовой таможенной декларации (ГТД), регистрационный номер партии товара (РНПТ), маркировку «Честный ЗНАК», другие маркировки или вес, чтобы перевести отправление в следующий статус.

- Тип: `object`
- Nullable: **нет**
- Ограничения: —

#### Поля

| Поле | Required | Тип / вложенная ссылка | Nullable | Ограничения и enum | Description |
| --- | --- | --- | --- | --- | --- |
| `products_requiring_change_country` | нет | array&lt;`string`&gt; | нет | — | Список идентификаторов товаров (SKU), для которых нужно изменить страну-изготовитель. Чтобы изменить страну-изготовитель, используйте методы [/v2/posting/fbs/product/country/list](#operation/PostingAPI_ListCountryProductFbsPostingV2) и [/v2/posting/fbs/product/country/set](#operation/PostingAPI_SetCountryProductFbsPostingV2). |
| `products_requiring_gtd` | нет | array&lt;`string`&gt; | нет | — | Список идентификаторов товаров (SKU), для которых нужно передать номера таможенной декларации (ГТД).<br><br>До сборки отправления передайте для всех перечисленных товаров номер таможенной декларации или информацию о том, <br>что номера нет, методом [/v6/fbs/posting/product/exemplar/set](#operation/PostingAPI_FbsPostingProductExemplarSetV6).<br> |
| `products_requiring_country` | нет | array&lt;`string`&gt; | нет | — | Список идентификаторов товаров (SKU), для которых нужно передать информацию о стране-изготовителе.<br><br>Для сборки отправления передайте информацию о стране-изготовителе для всех перечисленных товаров с помощью метода [/v2/posting/fbs/product/country/set](#operation/PostingAPI_SetCountryProductFbsPostingV2).<br> |
| `products_requiring_mandatory_mark` | нет | array&lt;`string`&gt; | нет | — | Список идентификаторов товаров (SKU), для которых нужно передать маркировку «Честный ЗНАК».<br><br>До сборки отправления передайте для всех перечисленных товаров маркировку «Честный ЗНАК» методом [/v6/fbs/posting/product/exemplar/set](#operation/PostingAPI_FbsPostingProductExemplarSetV6).<br> |
| `products_requiring_jw_uin` | нет | array&lt;`string`&gt; | нет | — | Список товаров, для которых нужно передать уникальный идентификационный номер (УИН) ювелирного изделия.<br><br>До сборки отправления передайте для всех перечисленных товаров уникальный идентификационный номер (УИН) методом [/v6/fbs/posting/product/exemplar/set](#operation/PostingAPI_FbsPostingProductExemplarSetV6).<br> |
| `products_requiring_rnpt` | нет | array&lt;`string`&gt; | нет | — | Список идентификаторов товаров (SKU), для которых нужно передать регистрационный номер партии товара (РНПТ).<br><br>До сборки отправления передайте для всех перечисленных товаров регистрационный номер партии товара (РНПТ) методом [/v6/fbs/posting/product/exemplar/set](#operation/PostingAPI_FbsPostingProductExemplarSetV6).<br> |
| `products_requiring_weight` | нет | array&lt;`string`&gt; | нет | — | Список товаров, для которых нужно передать вес. |
| `products_requiring_imei` | нет | array&lt;`string`&gt; | нет | — | Список идентификаторов товаров, для которых нужно передать IMEI. |

### v3FbsTariffication

<a id="schema-v3fbstariffication"></a>

Информация по тарификации отгрузки.

- Тип: `object`
- Nullable: **нет**
- Ограничения: —

#### Поля

| Поле | Required | Тип / вложенная ссылка | Nullable | Ограничения и enum | Description |
| --- | --- | --- | --- | --- | --- |
| `current_tariff_rate` | нет | `number` | нет | format=`"double"` | Текущий процент тарификации. |
| `current_tariff_type` | нет | `string` | нет | — | Текущий тип тарификации — скидка или надбавка. |
| `current_tariff_charge` | нет | `string` | нет | — | Текущая сумма скидки или надбавки. |
| `current_tariff_charge_currency_code` | нет | `string` | нет | — | Валюта суммы. |
| `next_tariff_rate` | нет | `number` | нет | format=`"double"` | Процент, по которому будет тарифицироваться отправление через указанное в параметре `next_tariff_starts_at` время. |
| `next_tariff_type` | нет | `string` | нет | — | Тип тарифа, по которому будет тарифицироваться отправление через указанное в параметре `next_tariff_starts_at` время — скидка или надбавка. |
| `next_tariff_charge` | нет | `string` | нет | — | Сумма скидки или надбавки на следующем шаге тарификации. |
| `next_tariff_starts_at` | нет | `string` | нет | format=`"date-time"` | Дата и время, когда начнёт применяться новый тариф.<br><br>Формат: `YYYY-MM-DDThh:mm:ss.mcsZ`. <br><br>Пример: `2023-11-13T08:05:57.657Z`.<br> |
| `next_tariff_charge_currency_code` | нет | `string` | нет | — | Валюта нового тарифа. |

### v3GetFbsPostingResponseV3

<a id="schema-v3getfbspostingresponsev3"></a>

- Тип: `object`
- Nullable: **нет**
- Ограничения: —

#### Поля

| Поле | Required | Тип / вложенная ссылка | Nullable | Ограничения и enum | Description |
| --- | --- | --- | --- | --- | --- |
| `result` | нет | [`v3FbsPostingDetail`](#schema-v3fbspostingdetail) | нет | — | — |

### v3PostingFinancialData

<a id="schema-v3postingfinancialdata"></a>

Данные о стоимости товара, размере скидки, выплате и комиссии.

- Тип: `object`
- Nullable: **нет**
- Ограничения: —

#### Поля

| Поле | Required | Тип / вложенная ссылка | Nullable | Ограничения и enum | Description |
| --- | --- | --- | --- | --- | --- |
| `cluster_from` | нет | `string` | нет | — | Код региона, откуда отправляется заказ. |
| `cluster_to` | нет | `string` | нет | — | Код региона, куда доставляется заказ. |
| `products` | нет | array&lt;[`PostingFinancialDataProduct`](#schema-postingfinancialdataproduct)&gt; | нет | — | Список товаров в заказе. |

### v3PostingProductDetail

<a id="schema-v3postingproductdetail"></a>

Размеры товара.

- Тип: `object`
- Nullable: **нет**
- Ограничения: —

#### Поля

| Поле | Required | Тип / вложенная ссылка | Nullable | Ограничения и enum | Description |
| --- | --- | --- | --- | --- | --- |
| `dimensions` | нет | [`v3Dimensions`](#schema-v3dimensions) | нет | — | — |
| `mandatory_mark` | нет | array&lt;`string`&gt; | нет | deprecated=`true` | Обязательная маркировка товара. |
| `name` | нет | `string` | нет | — | Название. |
| `offer_id` | нет | `string` | нет | — | Идентификатор товара в системе продавца — артикул. |
| `price` | нет | `string` | нет | — | Цена товара с учётом скидок — это значение показывается на карточке товара. |
| `jw_uin` | нет | `array of strings` | нет | — | Уникальный идентификационный номер (УИН) ювелирного изделия. |
| `currency_code` | нет | `string` | нет | — | Валюта ваших цен. Совпадает с валютой, которая установлена в настройках личного кабинета.<br><br>Возможные значения: <br>  - `RUB` — российский рубль,<br>  - `BYN` — белорусский рубль,<br>  - `KZT` — тенге,<br>  - `EUR` — евро,<br>  - `USD` — доллар США,<br>  - `CNY` — юань.<br> |
| `is_blr_traceable` | нет | `boolean` | нет | — | Признак прослеживаемости товара. |
| `is_marketplace_buyout` | нет | `boolean` | нет | — | `true`, если Ozon выкупил товар.<br><br>[Подробнее о выкупе товаров в Базе знаний продавца](https://seller-edu.ozon.ru/commissions-tariffs/commissions-tariffs-ozon/prodaji-tovarov-v-eaes-i-drugie-strany#какие-товары-выкупает-ozon)<br> |
| `quantity` | нет | `integer` | нет | format=`"int32"` | Количество товара. |
| `sku` | нет | `integer` | нет | format=`"int64"` | Идентификатор товара на Ozon. |
| `is_weight_needed` | нет | `boolean` | нет | — | `true`, если товар весовой.<br> |
| `weight_max` | нет | `number` | нет | format=`"float"` | Максимальный вес экземпляра. |
| `weight_min` | нет | `number` | нет | format=`"float"` | Минимальный вес экземпляра. |
| `has_imei` | нет | `boolean` | нет | — | Признак наличия IMEI.<br><br>Если IMEI есть — `true`.<br> |

### v4FbsPostingShipPackageV4Request

<a id="schema-v4fbspostingshippackagev4request"></a>

- Тип: `object`
- Nullable: **нет**
- Ограничения: —

#### Поля

| Поле | Required | Тип / вложенная ссылка | Nullable | Ограничения и enum | Description |
| --- | --- | --- | --- | --- | --- |
| `posting_number` | да | `string` | нет | — | Номер отправления. |
| `products` | нет | array&lt;[`v4FbsPostingShipPackageV4RequestProduct`](#schema-v4fbspostingshippackagev4requestproduct)&gt; | нет | — | Список товаров в отправлении. |

### v4FbsPostingShipPackageV4RequestProduct

<a id="schema-v4fbspostingshippackagev4requestproduct"></a>

- Тип: `object`
- Nullable: **нет**
- Ограничения: —

#### Поля

| Поле | Required | Тип / вложенная ссылка | Nullable | Ограничения и enum | Description |
| --- | --- | --- | --- | --- | --- |
| `exemplarsIds` | нет | array&lt;`string`&gt; | нет | — | Идентификаторы экземпляров товара. |
| `product_id` | да | `integer` | нет | format=`"int64"` | Идентификатор товара в системе продавца — SKU. |
| `quantity` | да | `integer` | нет | format=`"int32"` | Количество экземпляров. |

### v4FbsPostingShipPackageV4Response

<a id="schema-v4fbspostingshippackagev4response"></a>

- Тип: `object`
- Nullable: **нет**
- Ограничения: —

#### Поля

| Поле | Required | Тип / вложенная ссылка | Nullable | Ограничения и enum | Description |
| --- | --- | --- | --- | --- | --- |
| `result` | нет | `string` | нет | — | Номера отправлений, сформированные после сборки. |

### v5FbsPostingProductExemplarStatusV5Request

<a id="schema-v5fbspostingproductexemplarstatusv5request"></a>

- Тип: `object`
- Nullable: **нет**
- Ограничения: —

#### Поля

| Поле | Required | Тип / вложенная ссылка | Nullable | Ограничения и enum | Description |
| --- | --- | --- | --- | --- | --- |
| `posting_number` | да | `string` | нет | — | Номер отправления. |

### v5FbsPostingProductExemplarStatusV5Response

<a id="schema-v5fbspostingproductexemplarstatusv5response"></a>

- Тип: `object`
- Nullable: **нет**
- Ограничения: —

#### Поля

| Поле | Required | Тип / вложенная ссылка | Nullable | Ограничения и enum | Description |
| --- | --- | --- | --- | --- | --- |
| `posting_number` | нет | `string` | нет | — | Номер отправления. |
| `products` | нет | array&lt;[`v5FbsPostingProductExemplarStatusV5ResponseProduct`](#schema-v5fbspostingproductexemplarstatusv5responseproduct)&gt; | нет | — | Список товаров. |
| `status` | нет | `string` | нет | — | Статус проверки всех экземпляров и доступности сборки:<br> - `ship_available` — сборка доступна;<br> - `ship_not_available` — сборка недоступна;<br> - `validation_in_process` — экземпляры на проверке;<br> - `update_available` — редактирование информации об экземплярах доступно;<br> - `update_not_available` — редактирование информации об экземплярах недоступно.<br> |

### v5FbsPostingProductExemplarStatusV5ResponseProduct

<a id="schema-v5fbspostingproductexemplarstatusv5responseproduct"></a>

- Тип: `object`
- Nullable: **нет**
- Ограничения: —

#### Поля

| Поле | Required | Тип / вложенная ссылка | Nullable | Ограничения и enum | Description |
| --- | --- | --- | --- | --- | --- |
| `exemplars` | нет | array&lt;[`v5FbsPostingProductExemplarStatusV5ResponseProductExemplar`](#schema-v5fbspostingproductexemplarstatusv5responseproductexemplar)&gt; | нет | — | Информация об экземплярах. |
| `product_id` | нет | `integer` | нет | format=`"int64"` | Идентификатор товара в системе Ozon — SKU. |

### v5FbsPostingProductExemplarStatusV5ResponseProductExemplar

<a id="schema-v5fbspostingproductexemplarstatusv5responseproductexemplar"></a>

- Тип: `object`
- Nullable: **нет**
- Ограничения: —

#### Поля

| Поле | Required | Тип / вложенная ссылка | Nullable | Ограничения и enum | Description |
| --- | --- | --- | --- | --- | --- |
| `exemplar_id` | нет | `integer` | нет | format=`"int64"` | Идентификатор экземпляра. |
| `gtd` | нет | `string` | нет | — | Номер грузовой таможенной декларации (ГТД). |
| `gtd_check_status` | нет | `string` | нет | — | Статус проверки грузовой таможенной декларации. |
| `gtd_error_codes` | нет | array&lt;`string`&gt; | нет | — | Коды ошибок при проверке грузовой таможенной декларации. |
| `is_gtd_absent` | нет | `boolean` | нет | — | Признак того, что не указан номер таможенной декларации (ГТД). |
| `is_rnpt_absent` | нет | `boolean` | нет | — | Признак того, что не указан регистрационный номер партии товара (РНПТ). |
| `marks` | нет | array&lt;[`v5FbsPostingProductExemplarStatusV5ResponseProductExemplarMark`](#schema-v5fbspostingproductexemplarstatusv5responseproductexemplarmark)&gt; | нет | — | Список контрольных идентификационных знаков (КИЗ) и других маркировок в одном экземпляре. |
| `rnpt` | нет | `string` | нет | — | Регистрационный номер партии товара (РНПТ). |
| `rnpt_check_status` | нет | `string` | нет | — | Статус проверки регистрационного номера партии товара. |
| `rnpt_error_codes` | нет | array&lt;`string`&gt; | нет | — | Коды ошибок при проверке регистрационного номера партии товара. |
| `weight` | нет | `number` | нет | format=`"float"` | Фактический вес экземпляра. |
| `weight_check_status` | нет | `string` | нет | — | Статус проверки фактического веса. |
| `weight_error_codes` | нет | array&lt;`string`&gt; | нет | — | Коды ошибок при проверке фактического веса. |

### v5FbsPostingProductExemplarStatusV5ResponseProductExemplarMark

<a id="schema-v5fbspostingproductexemplarstatusv5responseproductexemplarmark"></a>

- Тип: `object`
- Nullable: **нет**
- Ограничения: —

#### Поля

| Поле | Required | Тип / вложенная ссылка | Nullable | Ограничения и enum | Description |
| --- | --- | --- | --- | --- | --- |
| `check_status` | нет | `string` | нет | — | Статус проверки:<br>  - `processing` — на проверке;<br>  - `failed` — система не успела обработать запрос;<br>  - `passed` — заказ готов к сборке.<br> |
| `error_codes` | нет | array&lt;`string`&gt; | нет | — | Ошибки при проверке контрольных идентификационных знаков (КИЗ) и других маркировок. |
| `mark` | нет | `string` | нет | — | Значение кода маркировки. |
| `mark_type` | нет | `string` | нет | — | Тип кода маркировки:<br> - `mandatory_mark` — обязательная маркировка «Честный ЗНАК»;<br> - `jw_uin` — уникальный идентификационный номер (УИН) ювелирного изделия;<br> - `imei` — IMEI мобильного устройства.<br> |

### v5FbsPostingProductExemplarValidateV5Request

<a id="schema-v5fbspostingproductexemplarvalidatev5request"></a>

- Тип: `object`
- Nullable: **нет**
- Ограничения: —

#### Поля

| Поле | Required | Тип / вложенная ссылка | Nullable | Ограничения и enum | Description |
| --- | --- | --- | --- | --- | --- |
| `posting_number` | да | `string` | нет | — | Номер отправления. |
| `products` | да | array&lt;[`v5FbsPostingProductExemplarValidateV5RequestProduct`](#schema-v5fbspostingproductexemplarvalidatev5requestproduct)&gt; | нет | — | Список товаров. |

### v5FbsPostingProductExemplarValidateV5RequestProduct

<a id="schema-v5fbspostingproductexemplarvalidatev5requestproduct"></a>

- Тип: `object`
- Nullable: **нет**
- Ограничения: —

#### Поля

| Поле | Required | Тип / вложенная ссылка | Nullable | Ограничения и enum | Description |
| --- | --- | --- | --- | --- | --- |
| `exemplars` | да | array&lt;[`v5FbsPostingProductExemplarValidateV5RequestProductExemplar`](#schema-v5fbspostingproductexemplarvalidatev5requestproductexemplar)&gt; | нет | — | Информация об экземплярах. |
| `product_id` | да | `integer` | нет | format=`"int64"` | Идентификатор товара в системе Ozon — SKU. |

### v5FbsPostingProductExemplarValidateV5RequestProductExemplar

<a id="schema-v5fbspostingproductexemplarvalidatev5requestproductexemplar"></a>

- Тип: `object`
- Nullable: **нет**
- Ограничения: —

#### Поля

| Поле | Required | Тип / вложенная ссылка | Nullable | Ограничения и enum | Description |
| --- | --- | --- | --- | --- | --- |
| `gtd` | нет | `string` | нет | — | Номер грузовой таможенной декларации (ГТД). |
| `marks` | нет | array&lt;[`v5FbsPostingProductExemplarValidateV5RequestProductExemplarMark`](#schema-v5fbspostingproductexemplarvalidatev5requestproductexemplarmark)&gt; | нет | — | Список контрольных идентификационных знаков (КИЗ) и других маркировок в одном экземпляре. |
| `rnpt` | нет | `string` | нет | — | Регистрационный номер партии товара (РНПТ). |
| `weight` | нет | `number` | нет | format=`"float"` | Фактический вес экземпляра. |

### v5FbsPostingProductExemplarValidateV5RequestProductExemplarMark

<a id="schema-v5fbspostingproductexemplarvalidatev5requestproductexemplarmark"></a>

- Тип: `object`
- Nullable: **нет**
- Ограничения: —

#### Поля

| Поле | Required | Тип / вложенная ссылка | Nullable | Ограничения и enum | Description |
| --- | --- | --- | --- | --- | --- |
| `mark` | нет | `string` | нет | — | Значение кода маркировки. |
| `mark_type` | нет | `string` | нет | — | Тип кода маркировки:<br> - `mandatory_mark` — обязательная маркировка «Честный ЗНАК»;<br> - `jw_uin` — уникальный идентификационный номер (УИН) ювелирного изделия;<br> - `imei` — IMEI мобильного устройства.<br> |

### v5FbsPostingProductExemplarValidateV5Response

<a id="schema-v5fbspostingproductexemplarvalidatev5response"></a>

- Тип: `object`
- Nullable: **нет**
- Ограничения: —

#### Поля

| Поле | Required | Тип / вложенная ссылка | Nullable | Ограничения и enum | Description |
| --- | --- | --- | --- | --- | --- |
| `products` | нет | array&lt;[`v5FbsPostingProductExemplarValidateV5ResponseProduct`](#schema-v5fbspostingproductexemplarvalidatev5responseproduct)&gt; | нет | — | Список товаров. |

### v5FbsPostingProductExemplarValidateV5ResponseProduct

<a id="schema-v5fbspostingproductexemplarvalidatev5responseproduct"></a>

- Тип: `object`
- Nullable: **нет**
- Ограничения: —

#### Поля

| Поле | Required | Тип / вложенная ссылка | Nullable | Ограничения и enum | Description |
| --- | --- | --- | --- | --- | --- |
| `error` | нет | `string` | нет | — | Код ошибки. |
| `exemplars` | нет | array&lt;[`v5FbsPostingProductExemplarValidateV5ResponseProductExemplar`](#schema-v5fbspostingproductexemplarvalidatev5responseproductexemplar)&gt; | нет | — | Информация об экземплярах. |
| `product_id` | нет | `integer` | нет | format=`"int64"` | Идентификатор товара в системе Ozon — SKU. |
| `valid` | нет | `boolean` | нет | — | Результат прохождения проверки. `true`, если коды всех экземпляров соответствуют требованиям. |

### v5FbsPostingProductExemplarValidateV5ResponseProductExemplar

<a id="schema-v5fbspostingproductexemplarvalidatev5responseproductexemplar"></a>

- Тип: `object`
- Nullable: **нет**
- Ограничения: —

#### Поля

| Поле | Required | Тип / вложенная ссылка | Nullable | Ограничения и enum | Description |
| --- | --- | --- | --- | --- | --- |
| `errors` | нет | array&lt;`string`&gt; | нет | — | Ошибки валидации экземпляра. |
| `gtd` | нет | `string` | нет | — | Номер грузовой таможенной декларации (ГТД). |
| `marks` | нет | array&lt;[`v5FbsPostingProductExemplarValidateV5ResponseProductExemplarMark`](#schema-v5fbspostingproductexemplarvalidatev5responseproductexemplarmark)&gt; | нет | — | Ошибки при проверке контрольных идентификационных знаков (КИЗ) и других маркировок. |
| `rnpt` | нет | `string` | нет | — | Регистрационный номер партии товара (РНПТ). |
| `valid` | нет | `boolean` | нет | — | Результат прохождения проверки. `true`, если код экземпляра соответствует требованиям. |
| `weight` | нет | `number` | нет | format=`"float"` | Фактический вес экземпляра. |

### v5FbsPostingProductExemplarValidateV5ResponseProductExemplarMark

<a id="schema-v5fbspostingproductexemplarvalidatev5responseproductexemplarmark"></a>

- Тип: `object`
- Nullable: **нет**
- Ограничения: —

#### Поля

| Поле | Required | Тип / вложенная ссылка | Nullable | Ограничения и enum | Description |
| --- | --- | --- | --- | --- | --- |
| `errors` | нет | array&lt;`string`&gt; | нет | — | Ошибки при проверке контрольных идентификационных знаков (КИЗ) и других маркировок. |
| `mark` | нет | `string` | нет | — | Значение кода маркировки. |
| `mark_type` | нет | `string` | нет | — | Тип кода маркировки:<br> - `mandatory_mark` — обязательная маркировка «Честный ЗНАК»;<br> - `jw_uin` — уникальный идентификационный номер (УИН) ювелирного изделия;<br> - `imei` — IMEI мобильного устройства.<br> |
| `valid` | нет | `boolean` | нет | — | Результат прохождения проверки. `true`, если контрольный идентификационный знак (КИЗ) и другие маркировки соответствуют требованиям. |

### v6FbsPostingProductExemplarCreateOrGetV6Request

<a id="schema-v6fbspostingproductexemplarcreateorgetv6request"></a>

- Тип: `object`
- Nullable: **нет**
- Ограничения: —

#### Поля

| Поле | Required | Тип / вложенная ссылка | Nullable | Ограничения и enum | Description |
| --- | --- | --- | --- | --- | --- |
| `posting_number` | да | `string` | нет | — | Номер отправления. |

### v6FbsPostingProductExemplarCreateOrGetV6Response

<a id="schema-v6fbspostingproductexemplarcreateorgetv6response"></a>

- Тип: `object`
- Nullable: **нет**
- Ограничения: —

#### Поля

| Поле | Required | Тип / вложенная ссылка | Nullable | Ограничения и enum | Description |
| --- | --- | --- | --- | --- | --- |
| `multi_box_qty` | нет | `integer` | нет | format=`"int32"` | Количество коробок, в которые упакован товар. |
| `posting_number` | нет | `string` | нет | — | Номер отправления. |
| `products` | нет | array&lt;[`FbsPostingProductExemplarCreateOrGetV6ResponseProduct`](#schema-fbspostingproductexemplarcreateorgetv6responseproduct)&gt; | нет | — | Список товаров. |

### v6FbsPostingProductExemplarSetV6Request

<a id="schema-v6fbspostingproductexemplarsetv6request"></a>

- Тип: `object`
- Nullable: **нет**
- Ограничения: —

#### Поля

| Поле | Required | Тип / вложенная ссылка | Nullable | Ограничения и enum | Description |
| --- | --- | --- | --- | --- | --- |
| `multi_box_qty` | нет | `integer` | нет | format=`"int32"` | Количество коробок, в которые упакован товар. |
| `posting_number` | да | `string` | нет | — | Номер отправления. |
| `products` | да | array&lt;[`FbsPostingProductExemplarSetV6RequestProducts`](#schema-fbspostingproductexemplarsetv6requestproducts)&gt; | нет | — | Список товаров. |
