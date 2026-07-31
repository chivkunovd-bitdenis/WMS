# 00 — Триаж

- **Задача:** Создание/наполнение FBS-отгрузки (WB supply), лист подбора, стикеры заказов.
- **Тип:** feature / **M**
- **Зависит от:** fbs-orders-intake ✅, fbs-seller-warehouse-token ✅ (токен)
- **Маршрут:** 0→1→ГЕЙТ1→2→3→4→5→6

## Затрагивает
models fbs_supply + FK fbs_order.supply_id + sticker fields; WB client supplies/stickers; service; API `/operations/fbs-supplies`.
