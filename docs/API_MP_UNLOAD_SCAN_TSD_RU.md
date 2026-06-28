# API scan-потока отгрузки на МП (TSD / Android)

**Контекст:** REQ-014, TASK-018. Мобильного клиента нет — контракт для будущего ТСД и стабильности web.

**Базовый префикс:** `/operations/marketplace-unload-requests/{request_id}`

## Канонический endpoint

`POST /boxes/{box_id}/scan`

Единая точка для scan-потока: **(опционально) ячейка → товар → строка короба**.

### Тело запроса

```json
{
  "barcode": "string",
  "storage_location_id": "uuid | null",
  "quantity": 1
}
```

- `storage_location_id` — запомненная ячейка после scan location (шаг 1); передаётся на шаге 2 (товар).
- `quantity` — по умолчанию 1; для товара можно > 1.

### Порядок (address storage **вкл.**)

1. Scan штрихкода **ячейки** → `200`, `kind: "location"`, `storage_location_id`, `location_code`. Строка короба **не** меняется.
2. Scan штрихкода **товара** с `storage_location_id` из шага 1 → `200`, `kind: "product"`, поля строки короба + `picked_qty` по документу.

Если у товара есть остатки в ячейках, а `storage_location_id` не передан → **422** `location_required`.

Если товар только в зоне сортировки — ячейка подставляется автоматически (DEC-005).

### Порядок (address storage **выкл.**)

1. Scan товара без `storage_location_id` → `200`, `kind: "product"`.

### Ответ `kind: "location"`

```json
{
  "kind": "location",
  "storage_location_id": "...",
  "location_code": "A-01-01"
}
```

### Ответ `kind: "product"`

```json
{
  "kind": "product",
  "storage_location_id": "...",
  "id": "line-uuid",
  "product_id": "...",
  "sku_code": "...",
  "product_name": "...",
  "quantity": 2,
  "picked_qty": 5
}
```

## Коды ошибок (единые для scan/collect)

| Код | HTTP | Когда |
|-----|------|--------|
| `location_required` | 422 | Адресное хранение вкл., товар в ячейках, ячейка не выбрана |
| `packaging_not_done` | 422 | Упаковка по отгрузке не завершена |
| `plan_limit_exceeded` | 422 | Сумма в коробах превысит план по SKU |
| `barcode_unknown` | 422 | Штрихкод не ячейка и не товар селлера |
| `box_closed` | 409 | Короб закрыт |
| `insufficient_available` | 422 | Нет остатка в ячейке |

## Deprecated

`POST /pick/scan` — legacy web inline-scan (открытый короб по `open_box_exists`). Для ТСД использовать **`POST /boxes/{box_id}/scan`**. Endpoint сохранён для обратной совместимости.

## Fallback без scan

- `POST /boxes/{box_id}/manual-line` — ручной ввод `{ product_id, storage_location_id?, quantity }`.
- Те же коды ошибок через collect.

## Preconditions

- Документ в статусе `confirmed`.
- Упаковка `done` (gate коробов).
- Короб открыт (`closed_at == null`) для scan в конкретный короб.
