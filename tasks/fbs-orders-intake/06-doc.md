# 06 — Док (срез)

## Бизнес
WMS сама забирает сборочные задания WB (схема «Маркетплейс» / FBS), маппит товар на каталог ФФ, бронирует штуку на складе и обновляет статус с WB — без работы в кабинете продавца на этом шаге.

## Технически
Домен `fbs_orders` + `fbs_order_reservations` + схема `fbs_order_markings`. Клиент `marketplace-api.wildberries.ru` в `wildberries_client`. Sync: job `wildberries_marketplace_orders_sync` и `POST /operations/fbs-orders/sync`. Токен v1 = supplies_token. Available ФБО вычитает и FBS-резервы.

## Почему так
`inventory_reservations` привязан к outbound-строке — для FBS зеркалируем паттерн ФБО (`marketplace_unload_reservations`).

## Follow-up
- Celery beat 2–5 мин
- Отдельный marketplace token (`fbs-seller-warehouse-token`)
- Advisory lock / serial sync против oversell
- Split `wb_marketplace_orders_service.py` (>400 строк)
