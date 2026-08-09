# Backend contract для полноценного FBS-процесса

> Этот контракт обязателен для Cursor. Имена внутренних классов можно уточнить, но URL, смысл полей, атомарность и коды ошибок нельзя менять без согласования с фронтом. Разделы 1–2 `FRONTEND_TASKS.md` являются частью wire-contract: там закреплены точные имена frontend-функций и полные TypeScript-формы ответов.

## 1. Общий envelope ошибок

Все новые FBS-ручки возвращают стабильную структуру:

```json
{
  "detail": {
    "code": "order_incompatible",
    "message": "Заказ нельзя добавить в выбранную поставку.",
    "context": {
      "order_id": "uuid",
      "reasons": ["different_wb_warehouse", "legal_type_mismatch"]
    },
    "retryable": false
  }
}
```

`message` — русский текст для оператора. `code` и `reasons` — стабильные машинные значения. Техническое тело ответа WB и токены наружу не выдавать.

HTTP mapping: `400` — malformed request, `401/403` — auth/tenant access, `404` — entity not found, `409` — бизнес-конфликт или stale preflight, `422` — валидный JSON с недопустимыми полями, `502` — однозначный отказ upstream WB, `503` — временная недоступность, `504` — timeout с неизвестным результатом. Для `409/502/503/504` envelope выше обязателен.

## 2. Список заказов

### `GET /operations/fbs-orders/worklist`

Query: `seller_id`, `status_group`, `search`, `limit`, `cursor`.

Ответ:

```json
{
  "items": [
    {
      "id": "uuid",
      "wb_order_id": 500010,
      "status": "new",
      "wb_status": "new",
      "seller": {"id": "uuid", "name": "Селлер 1"},
      "wb_warehouse": {"id": 501001, "name": "WB Москва"},
      "wms_warehouse": {"id": "uuid", "name": "Основной склад"},
      "product": {
        "id": "uuid",
        "name": "Футболка мужская",
        "image_url": "https://...",
        "seller_article": "ART-01",
        "wb_article": 123456,
        "barcode": "460000000001",
        "size": "L"
      },
      "inventory": {
        "available_unpacked": 4,
        "locations": [
          {"id": "uuid", "code": "A-01-02", "available_unpacked": 4}
        ]
      },
      "buyer_type": "individual",
      "cargo_type": "mgt",
      "can_pvz": true,
      "metadata": {
        "required": ["sgtin"],
        "optional": [],
        "states": [{"kind": "sgtin", "status": "missing", "reason": null}],
        "delivery_allowed": false
      },
      "sticker": {"status": "not_requested", "asset_url": null, "applied_at": null},
      "pick": {"status": "pending", "location_code": null, "picked_at": null},
      "pack": {"status": "pending", "packed_at": null},
      "created_at_wb": "2026-08-03T08:00:00Z",
      "deadline_at": "2026-08-08T08:00:00Z",
      "supply_id": null,
      "selection_blockers": []
    }
  ],
  "next_cursor": null,
  "server_now": "2026-08-03T10:00:00Z"
}
```

Правила:

- не делать N+1 по складам / остаткам / карточкам / маркировке;
- `available_unpacked` учитывает физический остаток и все резервы, включая FBS;
- `image_url` берётся из уже импортированной карточки WB;
- отсутствие товара, склада, остатка или карточки отображается явно, а не заменяется пустой строкой;
- цена в worklist не нужна.

## 3. Preflight состава

### `POST /operations/fbs-supplies/preflight`

```json
{
  "order_ids": ["uuid-1", "uuid-2"],
  "planned_delivery_type": "pvz"
}
```

Ответ 200 возвращается и для несовместимого набора:

```json
{
  "compatible": false,
  "summary": {
    "seller": {"id": "uuid", "name": "Селлер 1"},
    "wb_warehouse": {"id": 501001, "name": "WB Москва"},
    "wms_warehouse": {"id": "uuid", "name": "Основной склад"},
    "buyer_type": "individual",
    "cargo_type": "mgt",
    "orders_count": 2,
    "required_marking_count": 1,
    "pvz_allowed_count": 1,
    "pvz_blocked_count": 1,
    "nearest_deadline_at": "2026-08-08T08:00:00Z"
  },
  "issues": [
    {"order_id": "uuid-2", "code": "pvz_not_allowed", "message": "Заказ №500011 нельзя сдавать в ПВЗ."}
  ]
}
```

Проверки: seller, WB warehouse, WMS warehouse, buyer type, cargo type, status, deadline, existing supply, mapping, available reserve, `can_pvz`.

## 4. Атомарное создание поставки

### `POST /operations/fbs-supplies/from-orders`

```json
{
  "name": "FBS 03.08 утро",
  "order_ids": ["uuid-1", "uuid-2"],
  "planned_delivery_type": "warehouse_sc",
  "planned_destination": {
    "office_id": 123,
    "name": "СЦ Электросталь",
    "zone": "Москва"
  },
  "idempotency_key": "uuid-generated-by-client"
}
```

Требования:

- тот же validator, что в preflight, выполняется заново под DB lock;
- WB supply создаётся один раз;
- заказы добавляются актуальным batch-методом WB, чанками ≤100;
- локальная поставка не считается успешно созданной, пока WB не подтвердил состав;
- повтор с тем же idempotency key возвращает тот же результат;
- если WB supply создан, но добавление заказов завершилось неоднозначно, операция получает `pending_confirmation` / `failed`, сохраняет внешний ID и восстанавливается через reconcile. Нельзя создавать второй WB supply молча.
- успешный ответ — `FbsWorkspace` из `FRONTEND_TASKS.md`; отдельного сокращённого create-response нет.

## 5. Рабочее пространство поставки

### `GET /operations/fbs-supplies/{supply_id}/workspace`

Ответ содержит:

- header: номера, seller, WB warehouse, WMS warehouse, планируемый маршрут, зона, дедлайн;
- `stage`: `composition|picking|packing|order_stickers|handoff_prep|delivery|tracking`;
- `progress`: отдельные счётчики по подбору, упаковке, маркировке, стикерам и QR;
- `blockers`: список с `stage`, `code`, `message`, `order_id?`, `retryable`;
- полный состав заказов в формате worklist;
- `packaging_task_id` и объект задания упаковки либо безопасный URL его получения;
- грузоместа и печатные активы;
- `delivery_preflight`;
- `last_wb_sync_at`, `server_now`.

## 6. Переход к сборке

### `POST /operations/fbs-supplies/{supply_id}/start-work`

- body отсутствует;
- идемпотентно создаёт или возвращает существующий `PackagingTask`;
- переводит локальную поставку в рабочее состояние, но не закрывает её в WB;
- не создаёт отдельную FBS-упаковку;
- возвращает workspace.

## 7. Серверный подбор

### `POST /operations/fbs-supplies/{supply_id}/pick/scan-location`

Body: `{"location_barcode":"A-01-02"}`. Ответ — `FbsPickLocation`.

### `POST /operations/fbs-supplies/{supply_id}/pick/scan-product`

Body: `location_id`, `product_barcode`, optional `order_id`, `idempotency_key`.

Поведение:

- валидирует склад, ячейку, товар, seller ownership и остаток;
- выбирает конкретный ещё не подобранный заказ этого товара по ближайшему дедлайну, если `order_id` не передан;
- атомарно перемещает одну неупакованную единицу из исходной ячейки в сортировочную ячейку этого склада;
- сохраняет 1:1 pick record для конкретного заказа, пользователя, исходной ячейки и времени;
- повтор одного scan с тем же key не подбирает вторую единицу;
- другой клиент сразу видит обновлённый прогресс;
- ошибки: `wrong_location`, `wrong_product`, `insufficient_unpacked`, `order_already_picked`, `product_not_in_supply`, `seller_stock_mismatch`.
- успешный ответ — полный `FbsWorkspace`.

### `POST /operations/fbs-supplies/{supply_id}/pick/{order_id}/undo`

Разрешено только до упаковки. Возвращает товар в исходную ячейку, пишет обратное движение и аудит.
Body: `{"idempotency_key":"uuid"}`. Успешный ответ — полный `FbsWorkspace`.

## 8. Упаковка конкретной единицы

Существующий `PackagingTask` остаётся единственным документом упаковки. Его API расширяется так, чтобы каждое увеличение `qty_done` для FBS было связано с конкретным `FbsOrder`.

Минимальный результат операции упаковки:

```json
{
  "packaging_task": {"...": "existing fields"},
  "fulfilled_order": {
    "id": "uuid",
    "wb_order_id": 500010,
    "pack_status": "packed",
    "marking_status": "accepted",
    "sticker_status": "ready"
  }
}
```

Нельзя пометить конкретный заказ упакованным, пока он не подобран. Для одинаковых SKU порядок назначения — ближайший дедлайн, но UI может передать `order_id` после сканирования стикера / заказа.

## 9. Метаданные и маркировка

### `GET /operations/fbs-orders/{order_id}/metadata`

Возвращает `required`, `optional`, `states`, `delivery_allowed`, `last_checked_at` из фактического ответа WB.

### `POST /operations/fbs-orders/{order_id}/metadata/scan`

Body: `kind`, `raw_value`, `idempotency_key`.

- `raw_value` сохраняется без потери ASCII GS (`\u001d`);
- код проверяется на повторное использование и seller/product ownership;
- для КИЗ из пула сначала резервируется код конкретного seller/product;
- после подтверждённой пары товар ↔ код WMS автоматически отправляет метаданные WB;
- статус меняется по фактическому WB `metaDetails`;
- ручной override — отдельная admin-ручка с обязательной причиной и audit, не основной workflow.

## 10. Печатные активы

Frontend никогда не получает внутренний путь `fbs-stickers/...`.

### `POST /operations/fbs-supplies/{supply_id}/print-assets`

Body — `FbsPrintBatchRequest`, ответ — `FbsPrintBatch` из `FRONTEND_TASKS.md`. `order_ids` допустимы только для `kind=order_sticker`. `retry_missing=true` не перегенерирует уже готовые активы.

### `GET /operations/fbs-print-assets/{asset_id}/content`

Авторизованный binary response с реальным `Content-Type`; tenant/seller ownership проверяется до чтения. Для отсутствующего или чужого актива — structured `404`, не пустой `200`.

### `POST /operations/fbs-print-assets/{asset_id}/applied`

Body: `{"idempotency_key":"uuid"}`. Фиксирует пользователя и время фактического нанесения; возвращает `FbsPrintAsset`.

Каждый актив возвращается как:

```json
{
  "status": "ready",
  "content_type": "image/png",
  "width_mm": 58,
  "height_mm": 40,
  "download_url": "/operations/fbs-print-assets/{asset_id}/content",
  "preview_url": "/operations/fbs-print-assets/{asset_id}/content",
  "checksum": "sha256:..."
}
```

Контент отдаётся авторизованной binary-ручкой. Нужны операции:

- один стикер заказа;
- выбранные стикеры;
- все готовые стикеры поставки;
- retry только отсутствующих;
- QR одного / всех грузомест;
- QR поставки.

Batch-ответ обязан показать `requested`, `ready`, `missing`, `failed` и список заказов с ошибками. Пустой print window запрещён.

Подтверждение «наклеен» — отдельная серверная операция с пользователем и временем; открытие окна печати не равно нанесению.

## 11. Грузоместа ПВЗ

### `POST /operations/fbs-supplies/{supply_id}/cargo-places/preflight`

Body: список физических коробов с известными или введёнными размерами и весом.

### `POST /operations/fbs-supplies/{supply_id}/cargo-places`

Body: `count`, optional `boxes[]`, `idempotency_key`.

- не принимает `order_ids`;
- не требует `packaging_box_id`;
- проверяет count ≤ items + 1;
- проверяет ограничения ПВЗ по известным данным;
- ручное подтверждение допустимо только для отсутствующих данных и сохраняется в audit;
- после WB create выполняет GET reconcile и возвращает весь актуальный список.

### `GET /operations/fbs-supplies/{supply_id}/cargo-places`

Возвращает полный актуальный `FbsCargoPlace[]`; перед ответом reconcile не создаёт новые грузоместа.

### `DELETE /operations/fbs-supplies/{supply_id}/cargo-places`

Body: `wb_trbx_ids[]`, `idempotency_key`.

- только `pvz`, пока поставка в `draft|assembling|packed` (до deliver);
- вызывает WB `DELETE /api/v3/supplies/{supplyId}/trbx` с `{"trbxIds":[...]}`;
- после подтверждённого WB delete удаляет локальные `FbsTrbx` и связанные QR print assets только для запрошенных IDs;
- timeout → `pending_confirmation`; retry сверяет GET trbx list и считает отсутствующие **запрошенные** IDs подтверждённым delete без повторного удаления лишних мест;
- если часть запрошенных IDs ещё на WB, retry удаляет только их, не трогая уже исчезнувшие.

Удалить / deprecated сделать текущую обязательную ручку `/{trbx_id}/orders`. Она не участвует ни в одном gate.

## 12. Delivery preflight и передача

### `POST /operations/fbs-supplies/{supply_id}/delivery-preflight`

Перед расчётом выполняет свежий WB sync. Возвращает полный чек-лист и `can_deliver`.

### `POST /operations/fbs-supplies/{supply_id}/deliver`

Body: `idempotency_key`, `confirmed_preflight_version`.

- отклоняет устаревший preflight;
- вызывает WB один раз;
- локальный `in_delivery` только после однозначного успеха WB или reconcile, доказавшего, что поставка уже закрыта;
- timeout → `pending_confirmation`, а не success;
- 409 MetaValidationFail → список конкретных заказов / типов / причин;
- склад/СЦ: после успеха получает QR поставки;
- ПВЗ: требует созданные грузоместа и готовые QR до deliver.

### `POST /operations/fbs-supplies/{supply_id}/retry-supply-qr`

- Только `warehouse_sc` после подтверждённого deliver (`in_delivery` или `done`).
- Повторяет **только** fetch QR поставки (`GET barcode` / print-asset projection); **никогда** не вызывает WB deliver повторно.
- ПВЗ и поставки до deliver → `409 wrong_delivery_type` или `409 supply_bad_status`.
- Успешный ответ — полный `FbsWorkspace` с `supply.barcode_asset`.

## 13. Синхронизация после передачи

Фоновый sync обновляет поставки и отдельные заказы. Workspace показывает accepted / sorted / partially_rejected / cancelled / retry_required / done. При частичном отказе нужны конкретные order IDs, причина и оставшееся время.
