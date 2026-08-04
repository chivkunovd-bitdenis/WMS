# 02 — Арх-решение + стек  🔒 ГЕЙТ 1

## Наследование
Эпик `fbs-marketplace-orders`: Гейт 1 ✅ (Денис, 30.07.2026) — полный цикл FBS через WB Marketplace API v3, автоопрос, домен `fbs_*`.

## Уточнения модератора для этой под-задачи (2026-07-30)

| Тема | Решение | Почему |
|------|---------|--------|
| Резерв | Таблица `fbs_order_reservations` (1:1 с `fbs_order`), по образцу `marketplace_unload_reservations`. Available = on_hand − outbound − mp_unload − **fbs**. | `inventory_reservations` требует `outbound_shipment_line_id`; «вызов reserve()» в TASK — метафора, не API. |
| Токен | Пока `supplies_token_encrypted` → Authorization для Marketplace API. | Отдельного marketplace-токена ещё нет. |
| FK supply/trbx | `supply_id`, `trbx_id` — nullable UUID **без** FK. | Таблицы в следующих задачах. |
| Клиент | Функции в `wildberries_client.py` + base `wildberries_marketplace_api_base`; mock-флаг для тестов. | Как cards/supplies. |
| Сервис | `wb_marketplace_orders_service.py` — upsert, map, reserve, status sync. | Слои: logic в services. |
| Job | `JOB_TYPE_WILDBERRIES_MARKETPLACE_ORDERS_SYNC` + Celery task. | Как cards/supplies. |
| API | Минимум: start sync job + list orders (FF role). UI — out of scope. | Вертикальный срез без фронта. |

## 🔒 Подтверждение
- Эпик: ✅ Денис 30.07.2026
- Уточнения резерва/токена: модератор по запросу владельца «сам модерируй» / «делай по спеке» — **ок на код**.
