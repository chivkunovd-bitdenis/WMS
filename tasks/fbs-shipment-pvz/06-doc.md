# 06 — Док

## Бизнес
Для отгрузки в ПВЗ создаём грузоместа (короба), кладём туда заказы с лимитами WB (габариты/вес/≥2 заказа/объём), печатаем QR коробов и только потом передаём в доставку.

## Технически
`fbs_trbxes`, API `/operations/fbs-supplies/…/trbx…`, deliver для `pvz` требует `trbx_id` на каждом заказе.

## Follow-up
Lock supply на volume; packaging_box; негатив-тесты cross-supply/already_in_trbx.
