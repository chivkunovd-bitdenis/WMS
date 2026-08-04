# 02 — Арх-решение + стек  🔒 ГЕЙТ 1

## Принятое решение (Agent — continuous mode)

### 🔴 Fix 1 — `detach_cancelled_order_from_supply`
- **Подход:** единый сервисный путь `detach_order_from_supply(session, tenant_id, order)` в `fbs_packaging_integration_service.py`.
- Вызывается из `cancel_order` и `_apply_wb_status_to_order` при cancel-like статусе, если `order.supply_id` задан.
- Действия: `order.supply_id = None`, `order.trbx_id = None`; уменьшить `PackagingTaskLine.qty_total` на 1 (удалить строку если 0, не трогать `qty_confirmed_packed`); `try_promote_fbs_supply_if_ready`; если в supply 0 активных заказов → `supply.status = draft` (откат из assembling/packed).
- **Не** добавляем ASSEMBLING в `NON_CANCELLABLE` — отмена разрешена, но чистит отгрузку.

### 🟠 Fix 2 — маркировка перед PACKED
- `_supply_requires_marking`: для товаров с `requires_honest_sign` требовать sgtin с `check_status == ok` (или `no_check` если WB не проверяет).
- В `sync_fbs_order_statuses_all_sellers` после status-sync: для заказов supply в assembling — `sync_order_marking_statuses` батчами (лимит как у status sync).

### 🟡 Fix 3 — резерв
- Перед insert резерва: `SELECT … FROM fbs_order_reservations WHERE product_id=… AND warehouse_id=… FOR UPDATE` (блокировка строк резерва по продукту/складу).
- `_apply_wb_row_to_existing` → `_try_reserve_order` обернуть в `begin_nested` + `IntegrityError` → no-op (как у нового заказа).

### 🟡 Fix 4 — статус-синк
- Константа `STATUSES_ELIGIBLE_FOR_WB_SYNC` = все кроме terminal + sorted + in_delivery + done (явный frozenset).
- Пагинация: цикл offset/limit 500 пока batch не пустой; внутри одного seller за один вызов `sync_order_statuses`.

### Осознанно НЕ делаем
- #5 orphan WB/commit — документируем в 01-analysis.
- Удаление supply / packaging task при опустении — только draft, без DELETE.
- Celery lock на beat — достаточно FOR UPDATE.

### Миграции
- Нет.

## 🔒 Подтверждение человека (ГЕЙТ 1)
- **Статус:** ✅ Agent (continuous orchestrator, safe MVP defaults)
- **Кто и когда:** orchestrator, 2026-07-31
- **Комментарий:** развилки #1→A, #2→C из TASK.md
