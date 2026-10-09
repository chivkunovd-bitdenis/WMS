# API отчёта движения товаров

Версия: 1.0  
Базовый URL: `https://wms.sellerfocus.pro/api`

## Документация OpenAPI

- Swagger UI: `https://wms.sellerfocus.pro/api/docs/client`
- OpenAPI JSON: `https://wms.sellerfocus.pro/api/openapi-client.json`

## Авторизация

### Получение токена

```http
POST /auth/login
Content-Type: application/json
```

Тело запроса:

| Поле | Тип | Обязательное | Значение |
|---|---|---:|---|
| `email` | string | да | Email учётной записи селлера |
| `password` | string | да | Пароль учётной записи |
| `portal` | string | да | `seller` |

Пример:

```json
{
  "email": "seller@example.com",
  "password": "<password>",
  "portal": "seller"
}
```

Успешный ответ, HTTP 200:

```json
{
  "access_token": "<token>",
  "token_type": "bearer"
}
```

Токен передаётся во всех запросах к отчёту:

```http
Authorization: Bearer <token>
```

Доступные данные определяются учётной записью селлера. Параметр `seller_id` в методы отчёта не передаётся.

## Получение движений в JSON

```http
GET /reports/client-movements
Authorization: Bearer <token>
```

### Query-параметры

| Параметр | Тип | Обязательный | Ограничения |
|---|---|---:|---|
| `date_from` | ISO 8601 date-time | да | Начало периода включительно; часовой пояс обязателен |
| `date_to` | ISO 8601 date-time | да | Конец периода исключительно; часовой пояс обязателен |
| `sku` | string | нет | Точный код товара; нельзя передавать вместе с `shk` |
| `shk` | string | нет | Точный штрихкод; нельзя передавать вместе с `sku` |
| `marketplace` | string | нет | `wb` или `ozon` |
| `cursor` | string | нет | Курсор из поля `next_cursor` предыдущего ответа |
| `limit` | integer | нет | От 1 до 1000; значение по умолчанию 200 |

Период задаётся как `[date_from, date_to)`.

Пример запроса:

```bash
curl --get \
  'https://wms.sellerfocus.pro/api/reports/client-movements' \
  --header 'Authorization: Bearer <token>' \
  --data-urlencode 'date_from=2026-09-01T00:00:00Z' \
  --data-urlencode 'date_to=2026-10-01T00:00:00Z' \
  --data-urlencode 'marketplace=wb' \
  --data-urlencode 'limit=200'
```

### Ответ

HTTP 200, `application/json`:

```json
{
  "rows": [
    {
      "id": "4cd4e360-4130-4141-b5e3-a3f50dbc1464:0",
      "movement_id": "4cd4e360-4130-4141-b5e3-a3f50dbc1464",
      "occurred_at": "2026-09-12T12:00:00+00:00",
      "operation": "fbs_shipment",
      "warehouse_id": "00000000-0000-0000-0000-000000000001",
      "product_id": "00000000-0000-0000-0000-000000000002",
      "sku": "0007",
      "product_name": "Товар",
      "shk": "0000123456789",
      "size": "42",
      "marketplace": "ozon",
      "document": {
        "id": "00000000-0000-0000-0000-000000000003",
        "type": "fbs_order",
        "number": "OZ-702"
      },
      "quantity_delta": -1,
      "kiz": "0101234567890121\u001dSERIAL"
    }
  ],
  "next_cursor": null,
  "limit": 200
}
```

### Поля строки

| Поле | Тип | Nullable | Описание |
|---|---|---:|---|
| `id` | string | нет | Уникальный идентификатор строки отчёта |
| `movement_id` | UUID | нет | Идентификатор исходного движения |
| `occurred_at` | ISO 8601 date-time | нет | Дата и время движения |
| `operation` | enum | нет | Тип движения |
| `warehouse_id` | UUID | нет | Идентификатор склада |
| `product_id` | UUID | нет | Идентификатор товара |
| `sku` | string | нет | Код товара |
| `product_name` | string | нет | Наименование товара |
| `shk` | string | да | Штрихкод товара |
| `size` | string | да | Размер товара |
| `marketplace` | enum | да | `wb`, `ozon` или `null` |
| `document` | object | да | Связанный документ или заказ |
| `quantity_delta` | integer | нет | Приход — положительное число; расход — отрицательное |
| `kiz` | string | да | КИЗ отгруженной единицы FBS |

### Значения operation

| Значение | Операция | Знак quantity_delta |
|---|---|---|
| `inbound_intake` | Приёмка | положительный |
| `return` | Приём возврата | положительный |
| `fbs_shipment` | Отгрузка FBS | `-1` на каждую единицу |
| `marketplace_unload` | Отгрузка FBO | отрицательный |
| `inventory_count` | Инвентаризация | положительный или отрицательный, кроме 0 |

Резервы, отмены FBS и внутренние перемещения в ответ не включаются.

Для FBS одна строка ответа соответствует одной единице товара. Один `movement_id` может использоваться в нескольких строках; поле `id` остаётся уникальным.

### Поля document

| Поле | Тип | Обязательное | Описание |
|---|---|---:|---|
| `id` | string | да | Идентификатор документа |
| `type` | string | да | Тип документа |
| `number` | string | да | Номер документа или заказа |
| `status` | string | нет | Статус заявки FBO |
| `shipped_at` | ISO 8601 date-time или null | нет | Время завершения отгрузки FBO |

Возможные значения `document.type`: `inbound`, `return`, `fbs_order`, `marketplace_unload`, `inventory_count`.

### КИЗ

- `kiz` заполняется для отгруженной единицы FBS при наличии однозначной связи кода с заказом и товаром.
- При отсутствии сохранённого кода возвращается `null`.
- Значение передаётся полностью, включая ведущие нули.
- `\u001d` в JSON обозначает управляющий символ GS.
- Для FBO поле `kiz` равно `null`.

### Пагинация

1. Первый запрос выполняется без `cursor`.
2. Если `next_cursor` не равен `null`, его значение передаётся в параметре `cursor` следующего запроса.
3. Значения периода и остальных фильтров на следующих страницах не изменяются.
4. Выгрузка завершена при `next_cursor: null`.

Пустой результат:

```json
{
  "rows": [],
  "next_cursor": null,
  "limit": 200
}
```

## Получение отчёта в Excel

```http
GET /reports/client-movements/export.xlsx
Authorization: Bearer <token>
```

### Query-параметры

| Параметр | Тип | Обязательный | Ограничения |
|---|---|---:|---|
| `date_from` | ISO 8601 date-time | да | Начало периода включительно; часовой пояс обязателен |
| `date_to` | ISO 8601 date-time | да | Конец периода исключительно; часовой пояс обязателен |
| `sku` | string | нет | Точный код товара; нельзя передавать вместе с `shk` |
| `shk` | string | нет | Точный штрихкод; нельзя передавать вместе с `sku` |
| `marketplace` | string | нет | `wb` или `ozon` |

Метод не использует `cursor` и `limit`; в файл включается вся выборка.

Пример:

```bash
curl --get \
  'https://wms.sellerfocus.pro/api/reports/client-movements/export.xlsx' \
  --header 'Authorization: Bearer <token>' \
  --data-urlencode 'date_from=2026-09-01T00:00:00Z' \
  --data-urlencode 'date_to=2026-10-01T00:00:00Z' \
  --output client-movements.xlsx
```

Успешный ответ:

```http
HTTP/1.1 200 OK
Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet
Content-Disposition: attachment; filename="client-movements.xlsx"
```

Листы файла: `WB`, `Ozon`, `Общие`.

## Коды ответов

| Код | Описание |
|---:|---|
| 200 | Успешный запрос |
| 401 | Неверные реквизиты либо отсутствующий, недействительный или истёкший токен |
| 403 | Учётная запись не имеет права чтения отчёта |
| 422 | Ошибка параметров запроса |
| 429 | Превышен лимит попыток входа |
| 500 | Внутренняя ошибка сервера |

Ошибка авторизации:

```json
{
  "detail": "invalid_credentials"
}
```

Ошибка параметров:

```json
{
  "detail": "date_to must be after date_from"
}
```

Стандартная ошибка валидации:

```json
{
  "detail": [
    {
      "loc": ["query", "date_from"],
      "msg": "Field required",
      "type": "missing"
    }
  ]
}
```
