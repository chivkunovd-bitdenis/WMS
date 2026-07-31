# 06 — Док

## Бизнес
Отгрузку FBS (поток склад/СЦ) можно передать в доставку WB и получить QR поставки. Перед этим проверяются статусы заказов и КИЗ, если товар требует ЧЗ.

## Технически
`POST …/deliver`, `GET …/barcode`; lock supply+orders; кэш PNG в `wms_data_dir/fbs-supply-barcodes/`.

## Follow-up
Checklist; PG concurrency test; packaging packed-only; PVZ flow — отдельная задача.
