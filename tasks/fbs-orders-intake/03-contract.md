# 03 — Контракт (BA)

- **Что именно делаем (scope):** модели `fbs_order` / `fbs_order_marking` / `fbs_order_reservation` + миграция; HTTP-клиент Marketplace (`orders/new`, `orders`, `orders/status`); фоновый/ручной sync per-seller; маппинг product; резерв; `deadline_at = created_at_wb + 120h`; обновление `wb_status`.
- **Что НЕ делаем:** фронт, ТСД, supply/trbx/deliver, маркировка в WB, отмены как отдельный поток, отдельный marketplace_token, Ozon.

## Критерии приёмки
- [ ] Миграция создаёт таблицы; уникальность `(seller_id, wb_order_id)`.
- [ ] Sync новых заказов идемпотентен (повтор не плодит строки).
- [ ] Маппинг: barcode → nmId → product_id; иначе product_id NULL + флаг/пометка `mapping_missing`.
- [ ] При product_id и available≥1 — создаётся `fbs_order_reservation` qty=1; иначе заказ есть, резерва нет, пометка `no_stock` / без резерва.
- [ ] Status sync обновляет `wb_status`; при canceled — снятие резерва.
- [ ] `deadline_at` = created_at_wb + 120 часов.
- [ ] `pytest tests/test_fbs_orders_intake.py` зелёный; ruff/mypy на затронутом.

## Крайние случаи
- Дубликат wb_order_id; нулевой остаток; неизвестный баркод; ошибка WB (transport/4xx) — job failed с кодом, без частичного «тихого» успеха на весь seller без лога.

## Зависимости / допущения
- Токен = supplies_token до следующей задачи.
- Склад ФФ: warehouse_id селлера/тенанта — первый активный склад тенанта или явный параметр sync (зафиксировать в сервисе).
