# 06 — Док

## Бизнес
Селлер/ФФ может отменить FBS-заказ до отгрузки: заказ уходит в WB, резерв на складе снимается. Статусы с WB (выкуплен / отменён / брак / отсортирован) подтягиваются синком.

## Технически
`PATCH /operations/fbs-orders/{id}/cancel`, `POST …/sync-statuses`; матрица в `sync_order_statuses`; penalty band только в лог.

## Follow-up
Beat 5–10 мин; returns/disposal/fees; стабилизация SQLite combined flake; lock не держать на весь WB HTTP.
