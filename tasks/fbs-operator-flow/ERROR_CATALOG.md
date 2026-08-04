# Каталог ошибок FBS operator flow

> **Task:** FBSFLOW-130. Стабильные `code` для UI, логов и автотестов.  
> **Envelope (новые ручки):** см. `BACKEND_CONTRACT.md` §1 — `detail.code`, `detail.message` (RU), `detail.context`, `detail.retryable`.

## HTTP mapping (общее)

| HTTP | Когда | `retryable` по умолчанию |
|------|--------|---------------------------|
| 400 | Неверный запрос, бизнес-предусловие не выполнено | false |
| 401 / 403 | Auth / tenant / нет marketplace-токена | false |
| 404 | Сущность не найдена или чужой tenant | false |
| 409 | Конфlict, stale preflight, idempotency reuse, WB MetaValidationFail | false (кроме `operation_in_progress`) |
| 422 | Валидный JSON, недопустимые поля | false |
| 502 | Однозначный отказ WB upstream | false |
| 503 | Временная недоступность | true |
| 504 | Timeout / неизвестный результат WB (`wb_timeout`, `wb_pending_confirmation`) | **true** |

**Правило оператора:** при `retryable=true` UI показывает «повторите позже» и кнопку повтора; **никогда** не показывать локальный success при 504/неизвестном WB-ответе.

---

## Preflight / selection (`POST …/preflight`, `selection_blockers`)

| code | Сообщение (RU) | retryable |
|------|----------------|-----------|
| `different_seller` | Заказы принадлежат разным селлерам | false |
| `different_wb_warehouse` | Разные склады WB | false |
| `different_wms_warehouse` | Разные склады WMS | false |
| `legal_type_mismatch` | Смешаны B2C и B2B | false |
| `different_cargo_type` | Разный cargo type | false |
| `pvz_not_allowed` | Заказ нельзя сдавать в ПВЗ | false |
| `order_cancelled` | Заказ отменён или брак | false |
| `already_in_supply` | Заказ уже в поставке | false |
| `product_not_mapped` | Товар не сопоставлен с карточкой | false |
| `warehouse_unmapped` | Склад WB не привязан к WMS | false |
| `insufficient_stock` | Недостаточно неупакованного остатка | false |
| `deadline_passed` | Срок сборки истёк | false |
| `order_incompatible` | Обобщённый код при нескольких причинах | false |

---

## Создание поставки (`from-orders`, `start-work`)

| code | Сообщение (RU) | HTTP | retryable |
|------|----------------|------|-----------|
| `empty_order_set` | Не выбран ни один заказ | 400 | false |
| `missing_idempotency_key` | Нет ключа идемпотентности | 400 | false |
| `order_not_found` | Заказ не найден | 404 | false |
| `seller_not_found` | Селлер не найден | 404 | false |
| `warehouse_not_found` | Склад не найден | 404 | false |
| `missing_marketplace_token` | Нет токена WB Marketplace | 403 | false |
| `order_already_in_supply` | Заказ уже в другой поставке | 409 | false |
| `order_bad_status` | Статус заказа не позволяет добавление | 409 | false |
| `order_warehouse_mismatch` | Склад заказа не совпадает | 409 | false |
| `order_warehouse_unmapped` | Склад заказа не привязан | 409 | false |
| `invalid_delivery_type` | Недопустимый тип доставки | 400/409 | false |
| `order_incompatible` | Набор несовместим (с `context.reasons`) | 409 | false |
| `idempotency_key_reused` | Ключ уже использован с другим телом | 409 | false |
| `supply_not_editable` | Поставка не редактируется | 409 | false |
| `supply_empty` | Пустая поставка | 400 | false |
| `wb_timeout` | Таймаут WB, результат неизвестен | 504 | **true** |
| `wb_pending_confirmation` | Операция в WB не подтверждена | 504 | **true** |
| `operation_in_progress` | Параллельная операция | 504 | **true** |
| `wb_invalid_response` | Некорректный ответ WB | 502 | false |
| `wb_stickers_incomplete` | Не все стикеры получены от WB | 502 | false |

---

## Подбор (`pick/scan-*`, `pick/…/undo`)

| code | Сообщение (RU) | retryable |
|------|----------------|-----------|
| `wrong_location` | Неверная ячейка | false |
| `wrong_product` | Неверный товар / штрихкод | false |
| `insufficient_unpacked` | Недостаточно неупакованного в ячейке | false |
| `order_already_picked` | Заказ уже подобран | false |
| `product_not_in_supply` | Товар не входит в состав поставки | false |
| `seller_stock_mismatch` | Остаток другого селлера | false |
| `pick_not_found` | Запись подбора не найдена (undo) | false |
| `pick_already_packed` | Уже упакован — отмена подбора запрещена | false |

---

## Упаковка (`PackagingTask` + FBS fulfillment)

| code | Сообщение (RU) | retryable |
|------|----------------|-----------|
| `order_not_picked` | Заказ не подобран | false |
| `order_already_packed` | Заказ уже упакован | false |
| `order_not_in_supply` | Заказ не в этой поставке | false |
| `order_product_mismatch` | Товар не соответствует заказу | false |
| `no_eligible_order` | Нет подходящего заказа для SKU | false |
| `insufficient_unpacked` | Недостаточно в сортировке | false |
| `invalid_qty` | Недопустимое количество | false |
| `invalid_status_transition` | Недопустимый переход статуса | false |

---

## Маркировка / metadata

| code | Сообщение (RU) | retryable |
|------|----------------|-----------|
| `kind_not_required` | Тип метаданных не требуется для заказа | false |
| `kind_already_assigned` | Уже назначено | false |
| `invalid_kind` | Недопустимый тип | false |
| `empty_value` | Пустое значение | false |
| `duplicate_kiz` | КИЗ уже использован | false |
| `cross_seller_code` | КИЗ другого селлера | false |
| `code_product_mismatch` | КИЗ не соответствует товару | false |
| `order_marking_frozen` | Маркировка заморожена (поставка передана) | false |

WB 409 `MetaValidationFail` → `meta_validation_fail` с `context.orders[]` (order, kind, reason).

---

## Печать (`print-assets`, binary content)

| code | Сообщение (RU) | retryable |
|------|----------------|-----------|
| `invalid_kind` | Недопустимый kind печати | false |
| `invalid_order_ids` | order_ids не для этого kind | false |
| `file_missing` | Файл актива отсутствует | false |
| `empty_content` | Пустой файл | false |
| `checksum_mismatch` | Контрольная сумма не совпала | false |
| `invalid_content_type` | Неверный Content-Type | false |
| `invalid_storage_path` | Небезопасный путь (traversal) | false |
| `asset_not_found` | Актив не найден / чужой tenant | false |

Per-order batch: `ready` / `missing` / `failed` — не HTTP error; UI показывает счётчики и retry missing only.

---

## Грузоместа ПВЗ (`cargo-places`)

| code | Сообщение (RU) | retryable |
|------|----------------|-----------|
| `wrong_delivery_type` | Не ПВЗ-поставка | false |
| `invalid_trbx_count` | Недопустимое количество коробов | false |
| `trbx_count_exceeded` | Превышен лимит (≤ items + 1) | false |
| `trbx_oversized` | Сторона > 60 см | false |
| `trbx_sides_sum_exceeded` | Сумма сторон > 140 см | false |
| `trbx_overweight` | Вес > 5 кг | false |
| `trbx_volume_exceeded` | Объём > 1 м³ | false |
| `cargo_places_preflight_failed` | Preflight не пройден | false |
| `boxes_count_mismatch` | Число коробов не совпало с count | false |

**Deprecated:** `order_not_in_supply`, `order_already_in_trbx` на `POST …/trbx/{id}/orders` — ручка deprecated, не использовать.

---

## Передача в доставку (`delivery-preflight`, `deliver`)

| code | Сообщение (RU) | HTTP | retryable |
|------|----------------|------|-----------|
| `stale_preflight` | Чек-лист устарел — обновите | 409 | false |
| `packaging_required` | Не все заказы упакованы | 400 | false |
| `marking_required` | Обязательная маркировка не принята WB | 400 | false |
| `marking_not_allowed` | WB не разрешил доставку по meta | 400 | false |
| `cargo_places_required` | Нет грузомест (ПВЗ) | 400 | false |
| `cargo_place_qr_not_ready` | QR грузоместа не готов | 400 | false |
| `orders_not_ready` | Заказы не готовы | 400 | false |
| `supply_has_cancelled_orders` | В составе отменённые заказы | 400 | false |
| `order_cancelled` | Заказ отменён после sync | 400 | false |
| `supply_bad_status` | Неверный статус поставки | 409 | false |
| `meta_validation_fail` | WB отклонил metadata (409) | 409 | false |
| `wb_timeout` | Таймаут при закрытии | 504 | **true** |
| `wb_pending_confirmation` | Закрытие не подтверждено | 504 | **true** |

---

## Tracking (`sync-tracking`, autopoll)

| code | Сообщение (RU) | retryable |
|------|----------------|-----------|
| `supply_not_found` | Поставка не найдена | false |
| `missing_marketplace_token` | Нет токена | false |

Partial rejection: workspace `tracking_summary.partial_rejection` — не error code, а read-model с order IDs и причинами.

---

## Миграция со старого контракта

| Устарело | Замена |
|----------|--------|
| `sticker_file` / `barcode_file` в JSON | `download_url` / `preview_url` на print-asset |
| `POST …/stickers` → paths в ответе | `POST …/print-assets` |
| `POST …/trbx/{id}/orders` | Только count на `POST …/cargo-places` |
| Локальный checkbox «собран» | Серверный pick progress в workspace |
| `Product.requires_honest_sign` как gate | `requiredMeta` + фактический WB meta status |

Исторические TASK/SPEC в `tasks/fbs-frontend-*` и `tasks/fbs-marketplace-orders/SPEC.md` помечены deprecated; источник правды — этот каталог + `BACKEND_CONTRACT.md`.
