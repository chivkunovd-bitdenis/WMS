# 06 — Док

## Бизнес
Можно создать отгрузку (supply) в WB из WMS, положить в неё заказы, получить лист подбора и скачать/закэшировать стикеры заказов.

## Технически
`fbs_supplies` + API `/operations/fbs-supplies`; WB POST supplies / PATCH orders / POST stickers. Add order — `SELECT FOR UPDATE` на PostgreSQL.

## Follow-up
packaging_task; deliver; PG concurrency в CI; reconciliation orphan WB.
