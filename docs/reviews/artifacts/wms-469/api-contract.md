# WMS-469 — контракт API окна «Остаток для FBS»

Этот контракт описывает серверную часть принятого окна. Он одинаков для каталога
фулфилмента и кабинета селлера. Нового агрегирующего endpoint нет: окно, как и до
WMS-469, параллельно читает товары, живые справочники складов и сохранённые
привязки, а затем соединяет ответы по `binding_id`, `marketplace` и внешнему
идентификатору склада.

## 1. Права и границы

- Администратор фулфилмента читает и меняет привязки, `served` и товарные правила.
- Владелец/сотрудник селлера с правом `products` читает свои справочники,
  привязки и физические склады ФФ, а также читает и меняет правила только своих
  товаров текущего активного магазина.
- Для селлера `editable=false` в ответе привязки. Запросы изменения связки и
  `served` всё равно защищены сервером ролью администратора ФФ и отвечают `403`.
- Товар другого селлера/тенанта не возвращается: сервер отвечает `403` либо
  `404` в зависимости от проверяемого ресурса.

Заголовок авторизации и механизм выбора активного магазина остаются общими для
приложения. Нового права для WMS-469 нет.

## 2. Загрузка окна

Окно запускает следующие запросы параллельно.

### 2.1. Сохранённые привязки селлера

`GET /operations/fbs-sellers/{seller_id}/warehouse-bindings`

Ответ:

```json
[
  {
    "id": "11111111-1111-4111-8111-111111111111",
    "marketplace": "wb",
    "external_warehouse_id": null,
    "wb_warehouse_id": 501001,
    "wms_warehouse_id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
    "wms_warehouse_name": "Основной склад ФФ",
    "is_active": true,
    "served": true,
    "stock_sync_enabled": true,
    "last_sync_status": "confirmed",
    "last_sync_at": "2026-09-20T12:00:00Z",
    "last_error_code": null,
    "allocated_pool_total": 30,
    "editable": true
  },
  {
    "id": "22222222-2222-4222-8222-222222222222",
    "marketplace": "ozon",
    "external_warehouse_id": "1020005028840530",
    "wb_warehouse_id": 1020005028840530,
    "wms_warehouse_id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
    "wms_warehouse_name": "Основной склад ФФ",
    "is_active": true,
    "served": true,
    "stock_sync_enabled": true,
    "last_sync_status": null,
    "last_sync_at": null,
    "last_error_code": null,
    "allocated_pool_total": 0,
    "editable": true
  }
]
```

`id` — стабильный `binding_id`, которым ключуется новое товарное правило.
`stock_sync_enabled` — общий технический допуск транспорта привязки; это не
переключатель конкретного товара. Товарный переключатель находится в
`items[].by_binding[binding_id].publish`.

### 2.2. Живые названия складов продавца

Wildberries:

`GET /operations/fbs-sellers/{seller_id}/warehouses`

```json
[
  {
    "wb_warehouse_id": 501001,
    "id": 501001,
    "name": "Мой склад WB",
    "address": "Москва",
    "served": true,
    "wms_warehouse_id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
  }
]
```

Ozon:

`GET /operations/fbs-sellers/{seller_id}/ozon-warehouses`

```json
[
  {
    "warehouse_id": 1020005028840530,
    "name": "Мой склад Ozon",
    "has_entrusted_acceptance": false,
    "is_rfbs": false,
    "served": true,
    "wms_warehouse_id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
  }
]
```

Человеческое имя берётся только из соответствующего живого справочника. Для WB
ключ соединения — `wb_warehouse_id`; для Ozon — строковое
`external_warehouse_id` привязки и строковое представление `warehouse_id`.

Правила отображения при неполном справочнике:

- если справочник успешно загружен, привязка, которой в нём нет и у которой
  `served=false`, скрывается и не входит в суммы окна;
- уже сохранённая релевантная привязка не получает выдуманного имени: при сбое
  справочника показывается внешний идентификатор и ошибка загрузки имени;
- пока справочник не загружен полностью, добавление новой привязки недоступно;
- Ozon-блок скрывается при одном WB-only товаре; при массовом выборе он остаётся,
  если применим хотя бы к одному товару, а сервер применит его только к товарам
  с `applicable=true`.

### 2.3. Физические склады ФФ

`GET /warehouses`

```json
[
  {
    "id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
    "name": "Основной склад ФФ",
    "code": "MAIN",
    "barcode": "WH-MAIN",
    "is_operational": true
  }
]
```

Селлер использует этот ответ только для подписи уже выбранного склада. Контрол
выбора у него заблокирован. Администратор ФФ при единственном подходящем складе
может сразу подставить его в форму добавления; создание самой связки происходит
только после выбора обеих сторон.

### 2.4. Правила и рассчитанный остаток выбранных товаров

`POST /products/fbs-rule/bulk`

```json
{
  "product_ids": [
    "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
    "cccccccc-cccc-4ccc-8ccc-cccccccccccc"
  ]
}
```

Ответ сохраняет порядок уникальных `product_ids` из запроса:

```json
{
  "items": [
    {
      "product_id": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
      "publish": true,
      "publish_ozon": true,
      "same_everywhere": false,
      "percent": 0,
      "by_warehouse": {},
      "units_mode": true,
      "units_by_warehouse": {},
      "on_hand": 50,
      "reserved": 0,
      "free_stock": 50,
      "published_now": 75,
      "units_remaining_by_warehouse": {},
      "by_binding": {
        "11111111-1111-4111-8111-111111111111": {
          "publish": true,
          "mode": "units",
          "value": 30,
          "units_configured": true,
          "marketplace": "wb",
          "external_warehouse_id": "501001",
          "wms_warehouse_id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
          "served": true,
          "applicable": true,
          "on_hand": 50,
          "reserved": 0,
          "free_stock": 50,
          "published_now": 30
        },
        "22222222-2222-4222-8222-222222222222": {
          "publish": true,
          "mode": "percent",
          "value": 90,
          "units_configured": false,
          "marketplace": "ozon",
          "external_warehouse_id": "1020005028840530",
          "wms_warehouse_id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
          "served": true,
          "applicable": true,
          "on_hand": 50,
          "reserved": 0,
          "free_stock": 50,
          "published_now": 45
        }
      }
    }
  ]
}
```

Для WMS-469 источником состояния служит только `by_binding`. Поля верхнего
уровня оставлены для старых клиентов и не должны использоваться новым окном для
построения блоков.

Смысл полей одного блока:

- `publish` — публикация этого товара только в этой привязке;
- `mode` — ровно один режим: `percent` или `units`;
- `value` — сохранённый процент либо сохранённый ручной потолок;
- `units_configured` различает пустой поштучный лимит и явное число:
  `false` означает пустое поле, `true` вместе с `value=0` — явно введённый ноль;
- `on_hand`, `reserved`, `free_stock` — числа товара именно на связанном складе
  ФФ; глобальный резерв направления уже учтён;
- `published_now` — серверный расчёт для текущего сохранённого правила:
  `floor(free_stock * value / 100)` для процента либо
  `min(value, free_stock)` для числа;
- `applicable=false` у Ozon означает отсутствие активной карточки Ozon. Такой
  товар не включается в Ozon даже при массовом сохранении `publish=true`;
- `served=false` не стирает правило. Интерфейс показывает чип «Не принимаем
  заказы» и скрывает строку редактирования до обратного включения `served`.

Для сумм блока окно складывает `on_hand`, `reserved`, `free_stock` и
`published_now` по выбранным товарам для одного `binding_id`. В процентном
черновике число считается отдельно для каждого товара с округлением вниз, затем
складывается; нельзя умножать уже суммарный остаток один раз.

Одиночное чтение того же состояния доступно через
`GET /products/{product_id}/fbs-rule`.

## 3. Добавление и изменение связки

Связка и `served` сохраняются немедленно, независимо от кнопки сохранения
товарных правил.

`PUT /fbs-sellers/{seller_id}/warehouses/{external_warehouse_id}`

Добавление WB-связки:

```json
{
  "marketplace": "wb",
  "wms_warehouse_id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
  "served": true
}
```

Добавление Ozon-связки:

```json
{
  "marketplace": "ozon",
  "wms_warehouse_id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
  "served": true
}
```

Ответ:

```json
{
  "wb_warehouse_id": 501001,
  "id": 501001,
  "name": null,
  "served": true,
  "wms_warehouse_id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
  "address": null,
  "officeId": null,
  "cargoType": null,
  "deliveryType": null,
  "isDeleting": null,
  "isProcessing": null
}
```

`name=null` здесь нормально: имя остаётся данными живого справочника и не
дублируется в связке. После успеха окно перечитывает список привязок и соединяет
его со справочником.

Для смены физического склада ФФ отправляется тот же PUT с тем же
`external_warehouse_id`/`marketplace` и новым `wms_warehouse_id`. Для изменения
только `served` отправляется тот же PUT с новым `served`; текущий
`wms_warehouse_id` можно передать повторно. Не переданное поле существующей
связки не меняется.

Новая связка не включает товарную публикацию сама по себе. Публикация появится
после отдельного сохранения `by_binding` с `publish=true`. Повтор того же PUT
возвращает ту же уникальную связку и не создаёт дубль.

## 4. Сохранение правил выбранных товаров

`PUT /products/fbs-rule`

Запрос является атомарным для выбранных товаров. `by_binding` можно передать
частично: отсутствующая соседняя привязка не меняется. Обычно окно отправляет все
изменённые видимые блоки одним запросом.

Если ключ `by_binding` отсутствует, запрос считается старой формой и обрабатывается
по legacy-полям правила. Явно переданный пустой объект `by_binding: {}` считается
новой формой: он ничего не меняет и возвращает `updated_count: 0`.

Процент:

```json
{
  "product_ids": [
    "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
    "cccccccc-cccc-4ccc-8ccc-cccccccccccc"
  ],
  "rule": {
    "by_binding": {
      "11111111-1111-4111-8111-111111111111": {
        "publish": true,
        "mode": "percent",
        "value": 50
      },
      "22222222-2222-4222-8222-222222222222": {
        "publish": true,
        "mode": "percent",
        "value": 100
      }
    }
  }
}
```

`value` процента находится в диапазоне 0–100 и кратен 5. Между привязками нет
суммарного потолка: WB 100% и Ozon 100% разрешены.

Ручной потолок:

```json
{
  "product_ids": [
    "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
    "cccccccc-cccc-4ccc-8ccc-cccccccccccc"
  ],
  "rule": {
    "by_binding": {
      "11111111-1111-4111-8111-111111111111": {
        "publish": true,
        "mode": "units",
        "value": 50,
        "units_configured": true
      }
    }
  }
}
```

Чтобы очистить поштучный лимит и вернуть пустое поле, клиент отправляет тот же
блок с `mode="units"`, `units_configured=false`; `value` при этом нормализуется
сервером к нулю и не считается командой публикации нуля. `units_configured=true`
с `value=0` сохраняет именно явный операторский ноль и включает правила WMS-483.
Старый клиент WMS-469, который не передаёт `units_configured`, остаётся
совместимым: для режима `units` переданный `value` считается явным значением.

Если на связанном складе ФФ у первого товара свободно 50, а у второго 30,
сервер сохраняет 30 каждому товару и отвечает фактически сохранённым состоянием:

```json
{
  "updated_count": 2,
  "items": [
    {
      "product_id": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
      "publish": true,
      "publish_ozon": false,
      "same_everywhere": false,
      "percent": 0,
      "by_warehouse": {},
      "units_mode": true,
      "units_by_warehouse": {},
      "on_hand": 50,
      "reserved": 0,
      "free_stock": 50,
      "published_now": 30,
      "units_remaining_by_warehouse": {},
      "by_binding": {
        "11111111-1111-4111-8111-111111111111": {
          "publish": true,
          "mode": "units",
          "value": 30,
          "marketplace": "wb",
          "external_warehouse_id": "501001",
          "wms_warehouse_id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
          "served": true,
          "applicable": true,
          "on_hand": 50,
          "reserved": 0,
          "free_stock": 50,
          "published_now": 30
        }
      }
    }
  ],
  "clamps": {
    "11111111-1111-4111-8111-111111111111": {
      "requested_value": 50,
      "saved_value": 30,
      "limiting_product_id": "cccccccc-cccc-4ccc-8ccc-cccccccccccc",
      "limiting_product_name": "Ограничивающий товар"
    }
  }
}
```

В реальном ответе `items` содержит оба запрошенных товара; выше второй элемент
опущен только для краткости. Фронт обязан заменить черновое значение на
`saved_value` и показать подпись
`товара «Ограничивающий товар» всего 30 штук`. При равном минимуме сервер
возвращает первый такой товар в порядке `product_ids`.

Если обрезки не было, `clamps` — пустой объект. Отрицательное число, процент вне
0–100, процент не с шагом 5, неизвестная привязка, пустой/смешанный набор
селлеров отвечают `422`; неизвестный товар — `404`. Ошибка не означает успех, и
окно сохраняет пользовательский черновик для повторной попытки.

Выключение блока отправляет прежние `mode` и `value`, меняя только `publish`:

```json
{
  "product_ids": ["bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"],
  "rule": {
    "by_binding": {
      "11111111-1111-4111-8111-111111111111": {
        "publish": false,
        "mode": "units",
        "value": 30,
        "units_configured": true
      }
    }
  }
}
```

Так лимит сохраняется для повторного включения. Сервер перед фиксацией OFF один
раз подтверждает финальный ноль только выбранной привязке. Идентичный повтор уже
сохранённого OFF не посылает ноль повторно. Включение `publish=true` после commit
ставит немедленную публикацию текущего `min(value, free_stock)`.

Одиночное сохранение через `PUT /products/{product_id}/fbs-rule` принимает объект
из поля `rule` напрямую, но массовая ручка предпочтительна для окна: только она
возвращает `clamps` с ограничивающим товаром.

## 5. `served`

`served` означает только «принимаем заказы с этой привязки». Он не включает и не
выключает товарную публикацию и не стирает сохранённый лимит.

Изменение выполняет администратор ФФ тем же немедленным запросом связки:

`PUT /fbs-sellers/{seller_id}/warehouses/{external_warehouse_id}`

```json
{
  "marketplace": "wb",
  "wms_warehouse_id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
  "served": false
}
```

После ответа окно обновляет `served` локально или перечитывает привязки. Нажатие
«Отмена» товарного окна это изменение не откатывает. В кабинете селлера значение
только показывается; PUT от его имени сервер отклонит.

## 6. Повтор, конкуренция и публикация после commit

- Пара `binding_id + product_id` уникальна; повтор одного сохранения обновляет ту
  же строку `FbsBindingStockPool`.
- Два параллельных полных сохранения одного товара сериализуются блокировкой
  строки товара. Итог целиком равен одному запросу, без смеси полей.
- Повтор добавления одной внешней привязки возвращает одну строку, включая гонку
  двух одновременных вставок.
- После commit изменения правила или свободного остатка сервер запускает WB и
  Ozon независимо. Занятая блокировка не теряет событие. Ошибка или неполное
  подтверждение провайдера получает до трёх событийных попыток с паузой 1 с;
  периодическая сверка остаётся страховкой, а не первым путём.
- Операторские `value` не меняются резервом, заказом или движением. Пересчитывается
  только `free_stock` и производное `published_now`.
