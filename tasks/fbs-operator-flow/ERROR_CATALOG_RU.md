# Каталог ошибок FBS (стабильные коды backend)

Источник правды — `backend/app/services/fbs_*.py` и маппинг в `backend/app/api/fbs_*.py`.
Envelope для **всех новых** operator-facing FBS-ручек (см. `BACKEND_CONTRACT.md` §1; реализация — `backend/app/api/fbs_errors.py`):

```json
{
  "detail": {
    "code": "order_incompatible",
    "message": "Заказ нельзя добавить в выбранную поставку.",
    "context": {},
    "retryable": false
  }
}
```

Поля `code`, `message`, `context`, `retryable` обязательны. Вложенный `detail.detail` запрещён. Legacy create/add-order и deprecated sticker/barcode path могут ещё отдавать строковый `detail` — новый frontend их не использует.

`retryable=true` — клиент может повторить тот же запрос с тем же `idempotency_key` после паузы.
Префикс `wb_` — ошибка upstream Wildberries; `wb_timeout` / `wb_pending_confirmation` / `operation_in_progress` — результат на стороне WB неизвестен.

## HTTP mapping (общий)

| HTTP | Когда |
|------|--------|
| 400 | Некорректный запрос, бизнес-предусловие не выполнено |
| 403 | Нет токена маркетплейса (`missing_marketplace_token`) |
| 404 | Сущность не найдена |
| 409 | Конфликт состояния, stale preflight, дубликат маркировки |
| 422 | Валидный JSON, недопустимые поля (print-assets) |
| 502 | Однозначный отказ WB (`wb_*`, кроме timeout) |
| 503 | Операция уже выполняется (`operation_in_progress`) |
| 504 | Timeout / pending confirmation (`wb_timeout`, `wb_pending_confirmation`) |

---

## Поставка — preflight и создание (`FbsSupplyError`)

| code | HTTP | retryable | Описание (RU) |
|------|------|-----------|---------------|
| `empty_order_set` | 400 | false | Пустой список заказов |
| `missing_idempotency_key` | 400 | false | Не передан ключ идемпотентности |
| `supply_empty` | 400 | false | Поставка без заказов |
| `invalid_delivery_type` | 409 | false | Недопустимый тип доставки |
| `seller_not_found` | 404 | false | Селлер не найден |
| `warehouse_not_found` | 404 | false | WMS-склад не найден |
| `missing_marketplace_token` | 403 | false | Нет токена WB маркетплейса |
| `order_not_found` | 404 | false | Заказ не найден |
| `order_already_in_supply` | 409 | false | Заказ уже в другой поставке |
| `order_bad_status` | 409 | false | Заказ в недопустимом статусе |
| `order_warehouse_unmapped` | 409 | false | WB-склад заказа не привязан к WMS |
| `order_warehouse_mismatch` | 409 | false | Склад заказа не совпадает с поставкой |
| `supply_not_editable` | 409 | false | Поставку нельзя изменить |
| `supply_not_found` | 404 | false | Поставка не найдена |
| `order_incompatible` | 409 | false | Заказы несовместимы (см. `context.reasons`) |
| `idempotency_key_reused` | 409 | false | Ключ идемпотентности с другими параметрами |
| `wb_invalid_response` | 502 | false | Некорректный ответ WB |
| `wb_timeout` | 504 | **true** | Timeout при вызове WB |
| `wb_pending_confirmation` | 504 | **true** | WB не подтвердил результат; нужен reconcile |
| `operation_in_progress` | 504 | **true** | Операция создания уже выполняется |
| `wb_stickers_incomplete` | 500 | false | WB вернул неполный набор стикеров |
| `wb_*` | 502 | см. контекст | Прочие ошибки WB client |

### Коды preflight issues (`context`, не всегда top-level HTTP)

| code | retryable | Описание (RU) |
|------|-----------|---------------|
| `different_seller` | false | Разные селлеры в одном наборе |
| `different_wb_warehouse` | false | Разные склады WB |
| `different_wms_warehouse` | false | Разные WMS-склады |
| `legal_type_mismatch` | false | Смешение B2C и B2B |
| `different_cargo_type` | false | Разный тип груза |
| `pvz_not_allowed` | false | Заказ нельзя сдавать в ПВЗ |
| `insufficient_stock` | false | Недостаточно неупакованного остатка |
| `deadline_passed` | false | Дедлайн заказа прошёл |

---

## Подбор (`FbsPickingError`)

| code | HTTP | retryable | Описание (RU) |
|------|------|-----------|---------------|
| `supply_not_found` | 404 | false | Поставка не найдена |
| `wrong_location` | 409 | false | Ячейка не найдена или не та зона |
| `wrong_product` | 409 | false | Товар не найден по штрихкоду |
| `seller_stock_mismatch` | 409 | false | Товар другого селлера |
| `product_not_in_supply` | 409 | false | Товар не в составе / уже подобран |
| `order_already_picked` | 409 | false | Заказ уже подобран |
| `insufficient_unpacked` | 409 | false | Недостаточно остатка в ячейке |
| `pick_undo_not_allowed` | 409 | false | Отмена после упаковки запрещена |
| `order_not_picked` | 409 | false | Заказ ещё не подобран |

---

## Упаковка FBS (`FbsPackagingIntegrationError`)

| code | HTTP | retryable | Описание (RU) |
|------|------|-----------|---------------|
| `supply_not_found` | 404 | false | Поставка не найдена |
| `trbx_not_found` | 404 | false | Грузоместо не найдено |
| `wrong_delivery_type` | 400 | false | Неверный тип доставки |
| `invalid_status_transition` | 400 | false | Недопустимый переход статуса |
| `order_not_in_supply` | 500 | false | Заказ не в этой поставке |
| `order_product_mismatch` | 500 | false | Товар не совпадает с заказом |
| `order_not_picked` | 500 | false | Заказ не подобран |
| `order_already_packed` | 500 | false | Заказ уже упакован |
| `no_eligible_order` | 500 | false | Нет подходящего заказа для упаковки |
| `invalid_qty` | 500 | false | Недопустимое количество |
| `insufficient_unpacked` | 500 | false | Недостаточно неупакованного остатка |
| `packaging_box_already_bound` | 409 | false | Короб уже привязан к другому грузоместу |
| `packaging_box_not_found` | 404 | false | Короб не найден в складе этой поставки |
| `missing_fbs_packaging_location` | 500 | false | Для упакованного заказа не найдена исходная ячейка |
| `ambiguous_fbs_packaging_fulfillment` | 500 | false | У заказа несколько активных подтверждений упаковки (инвариант данных) |
| `fbs_packaging_product_mismatch` | 500 | false | Товар строки упаковки не совпадает с товаром заказа (инвариант данных) |

---

## Маркировка и метаданные (`FbsMarkingError`)

| code | HTTP | retryable | Описание (RU) |
|------|------|-----------|---------------|
| `order_not_found` | 404 | false | Заказ не найден |
| `seller_not_found` | 404 | false | Селлер не найден |
| `missing_marketplace_token` | 403 | false | Нет токена WB |
| `invalid_kind` | 400 | false | Неизвестный тип идентификатора |
| `empty_value` | 400 | false | Пустое значение |
| `kind_not_required` | 400 | false | Идентификатор не требуется |
| `order_marking_frozen` | 409 | false | Маркировка заморожена |
| `duplicate_kiz` | 409 | false | КИЗ уже использован |
| `cross_seller_code` | 409 | false | Код принадлежит другому селлеру |
| `code_product_mismatch` | 409 | false | Код не соответствует товару |
| `kind_already_assigned` | 409 | false | Идентификатор уже назначен |
| `meta_validation_fail` | 409 | false | WB отклонил метаданные |
| `marking_code_already_assigned` | 409 | false | Код маркировки уже назначен другому заказу |
| `sgtin_missing_gs` | 409 | false | КИЗ без GS-разделителя после серийного номера — WB его отклонит (I5) |
| `wb_*` | 502 | см. контекст | Ошибка WB |

---

## Печать активов (`FbsPrintAssetError`)

| code | HTTP | retryable | Описание (RU) |
|------|------|-----------|---------------|
| `supply_not_found` | 404 | false | Поставка не найдена |
| `order_not_in_supply` | 404 | false | Заказ не в поставке |
| `invalid_kind` | 422 | false | Неизвестный тип актива |
| `invalid_order_ids` | 422 | false | Пустой список заказов |
| `asset_not_ready` | 500 | **true** | Актив ещё не готов — повторить batch |
| `asset_error` | 500 | **true** | Ошибка получения от WB — retry missing |
| `wb_*` | 502 | см. envelope | Ошибка WB |

---

## Передача в доставку (`FbsShipmentError`)

| code | HTTP | retryable | Описание (RU) |
|------|------|-----------|---------------|
| `supply_not_found` | 404 | false | Поставка не найдена |
| `seller_not_found` | 404 | false | Селлер не найден |
| `missing_marketplace_token` | 403 | false | Нет токена WB |
| `wrong_delivery_type` | 400 | false | Неверный тип доставки |
| `supply_empty` | 400 | false | Пустая поставка |
| `supply_has_cancelled_orders` | 400 | false | Есть отменённые заказы |
| `orders_not_ready` | 400 | false | Заказы не готовы |
| `packaging_required` | 400 | false | Требуется упаковка |
| `marking_required` | 400 | false | Требуется маркировка |
| `marking_not_allowed` | 400 | false | Маркировка не разрешена WB |
| `invalid_barcode_path` | 400 | false | Некорректный путь QR |
| `cargo_places_required` | 400 | false | Нужны грузоместа (ПВЗ) |
| `cargo_place_qr_not_ready` | 400 | false | QR грузомест не готов |
| `missing_idempotency_key` | 400 | false | Нет ключа идемпотентности |
| `order_cancelled` | 400 | false | Заказ отменён на WB |
| `supply_bad_status` | 409 | false | Неверный статус поставки |
| `stale_preflight` | 409 | false | Чек-лист устарел — обновить preflight |
| `idempotency_key_reused` | 409 | false | Ключ с другими параметрами |
| `meta_validation_fail` | 409 | false | WB отклонил метаданные при deliver |
| `operation_in_progress` | 503 | **true** | Deliver уже выполняется |
| `wb_timeout` | 504 | **true** | Timeout WB |
| `wb_pending_confirmation` | 504 | **true** | Результат deliver не подтверждён |
| `wb_*` | 502 | см. контекст | Прочие ошибки WB |

---

## ПВЗ — грузоместа (`FbsShipmentPvzError`)

| code | HTTP | retryable | Описание (RU) |
|------|------|-----------|---------------|
| `supply_not_found` | 404 | false | Поставка не найдена |
| `seller_not_found` | 404 | false | Селлер не найден |
| `trbx_not_found` | 404 | false | Грузоместо не найдено |
| `missing_marketplace_token` | 403 | false | Нет токена WB |
| `wrong_delivery_type` | 400 | false | Не ПВЗ-поставка |
| `trbx_oversized` | 400 | false | Превышена сторона |
| `trbx_sides_sum_exceeded` | 400 | false | Превышена сумма сторон |
| `trbx_overweight` | 400 | false | Превышен вес |
| `trbx_min_orders` | 400 | false | Мало заказов в грузоместе |
| `trbx_volume_exceeded` | 400 | false | Превышен объём |
| `trbx_count_exceeded` | 500 | false | Слишком много грузомест |
| `order_not_in_supply` | 400 | false | Заказ не в поставке |
| `order_already_in_trbx` | 400 | false | Заказ уже в грузоместе |
| `invalid_trbx_count` | 400 | false | Недопустимое количество |
| `invalid_sticker_path` | 400 | false | Некорректный путь QR |
| `boxes_count_mismatch` | 400 | false | Число коробов не совпадает |
| `cargo_places_preflight_failed` | 400 | false | Preflight грузомест не пройден |
| `missing_idempotency_key` | 400 | false | Нет ключа идемпотентности |
| `idempotency_key_reused` | 409 | false | Ключ с другими параметрами |
| `wb_*` | 502 | см. контекст | Ошибка WB |

---

## Склады и привязки (`FbsWarehouseBindingError`, `FbsSellerWarehouseError`)

| code | HTTP | retryable | Описание (RU) |
|------|------|-----------|---------------|
| `seller_not_found` | 404 | false | Селлер не найден |
| `binding_not_found` | 404 | false | Привязка не найдена |
| `warehouse_not_found` | 400 | false | Склад не найден |
| `invalid_wb_warehouse_id` | 400 | false | Некорректный ID склада WB |
| `wms_warehouse_already_bound` | 409 | false | WMS-склад уже привязан |
| `active_fbs_reservations` | 409 | false | Есть активные FBS-резервы |
| `missing_marketplace_token` | 403 | false | Нет токена WB |
| `wb_*` | 502 | см. контекст | Ошибка WB |

---

## Синхронизация остатков (`FbsStockSyncError`)

| code | HTTP | retryable | Описание (RU) |
|------|------|-----------|---------------|
| `seller_not_found` | 404 | false | Селлер не найден |
| `missing_marketplace_token` | 500 | false | Нет токена WB |
| `binding_mismatch` | 500 | false | Привязка склада не совпадает |
| `duplicate_chrt_id` | — | false | Дубликат chrtId в каталоге |
| `readback_mismatch` | — | **true** | Readback WB не совпал — повтор sync |
| `sync_busy` | — | **true** | Sync уже выполняется |

---

## Отмена заказа (`FbsCancellationError`)

| code | HTTP | retryable | Описание (RU) |
|------|------|-----------|---------------|
| `order_not_found` | 404 | false | Заказ не найден |
| `order_not_cancellable` | 400 | false | Заказ нельзя отменить |
| `wb_*` | 502 | см. контекст | Ошибка WB |

---

## Трекинг после доставки (`FbsTrackingError`)

| code | HTTP | retryable | Описание (RU) |
|------|------|-----------|---------------|
| `supply_not_found` | 404 | false | Поставка не найдена |
| `supply_not_in_delivery` | 400 | false | Поставка не в доставке |
| `seller_not_found` | 404 | false | Селлер не найден |
| `missing_marketplace_token` | 403 | false | Нет токена WB |
| `wb_*` | 502 | **true** для transport | Ошибка WB |

---

## Workspace (`FbsWorkspaceError`)

| code | HTTP | retryable | Описание (RU) |
|------|------|-----------|---------------|
| `supply_not_found` | 404 | false | Поставка не найдена |

---

Обновлять этот файл при добавлении новых `Fbs*Error.code` в backend. Frontend должен ветвиться по `code`, не по тексту `message`.
