# 01 — Анализ

## Продукт
Селлер продаёт на WB по схеме «Маркетплейс» (FBS: товар лежит на складе ФФ, заказ собираем и отвозим в WB). WMS должна сама забирать новые сборочные задания из WB API, бронировать штуку на складе и дальше вести цикл без кабинета WB.

## Техника (факт из кода)
- WB-клиент сейчас только Content/Supplies (`wildberries_client.py`); Marketplace host (`marketplace-api.wildberries.ru`) ещё нет.
- Токены: `content_token` + `supplies_token` в `seller_wildberries_credentials`. Отдельного `marketplace_token` нет (задача `fbs-seller-warehouse-token`).
- `InventoryReservation` жёстко привязан к `outbound_shipment_line_id` — универсального `reserve()` нет.
- ФБО резервирует через отдельную таблицу `marketplace_unload_reservations` и вычитает её из available вместе с outbound.
- Product уже имеет `wb_barcode`, `wb_nm_id`, `wb_chrt_id` — маппинг естественный.
- Фоновые джобы: `BackgroundJob` + Celery/BackgroundTasks (`wildberries_cards_sync`, `wildberries_supplies_sync`).

## Вопросы (закрыты модератором — владелец: «сам модерируй»)
1. Резерв: не ломать FK outbound → отдельная `fbs_order_reservations` по образцу ФБО.
2. Токен v1: использовать `supplies_token` как временный Marketplace-токен до `fbs-seller-warehouse-token`.
3. `supply_id`/`trbx_id`: nullable UUID без FK (таблицы появятся в следующих задачах).
4. Периодичность: job type + сервис sync; ручной старт через API как у существующих WB sync; интервал 2–5 мин — конфиг/док, полноценный cron — follow-up если в репо нет scheduler.

## Стек (из эпика)
SQLAlchemy + Alembic, httpx, BackgroundJob/Celery, Fernet-токены.
