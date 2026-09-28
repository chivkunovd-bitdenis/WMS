-- WMS-447: тестовый набор для постановки и приёмки. Только для локальной тестовой
-- базы (wms447_ba_20260914), не для боя. Тенант — bootstrap «WMS Test».
-- Смысл набора: у селлера А пять поставок в разных состояниях, у селлера Б —
-- одна проведённая поставка Ozon. Даты — московские сутки. Факты операций
-- (OperationFact) для Ozon не заводятся, поэтому «Отгружено FBS» у селлера Б
-- останется 0 — число коробов от этого зависеть не должно.
--
--   A-1  WB, проведена 10.09.2026 00:30 МСК (в UTC ещё 09.09 21:30), 2 заказа, 3 короба
--   A-2  WB, проведена 12.09.2026 09:00 МСК, 1 заказ, 1 короб
--   A-3  WB, упакована (packed), не проведена, 2 короба      -> в отчёт не попадает
--   A-4  WB, status=done из кабинета WB, delivered_at NULL, 0 коробов -> не попадает
--   A-5  WB, проведена 13.09.2026 23:30 МСК (UTC 20:30), 1 заказ, 0 коробов (мягкая проверка
--        «в поставке пока нет коробов» не запрещает передачу)
--   B-1  Ozon, проведена 11.09.2026 15:00 МСК, 1 заказ, 2 короба
--
-- Ожидание для «Коробов FBS» (проверено запросом по этому набору 14.09.2026):
--   все селлеры: 09.09 → 0; 10.09 → 3; 12.09 → 1; 13.09 → 0; 14.09 → 0;
--   10.09–13.09 → 6; 01.09–14.09 → 6 (A-3 и A-4 не считаются никогда);
--   селлер А за 10–13.09 → 4; селлер Б за 10–13.09 → 2.
-- «Отгружено FBS» за 10–13.09 при этом остаётся 4 шт. (заказы WB A-1, A-2, A-5).

BEGIN;

WITH t AS (SELECT id AS tenant_id FROM tenants WHERE slug = 'wms-test'),
w AS (
  INSERT INTO warehouses (id, tenant_id, name, code)
  SELECT '11111111-0000-4000-8000-000000000001'::uuid, tenant_id, 'Склад 447', 'W447' FROM t
  ON CONFLICT (id) DO NOTHING
  RETURNING id
),
s AS (
  INSERT INTO sellers (id, tenant_id, name)
  SELECT '22222222-0000-4000-8000-00000000000a'::uuid, tenant_id, 'ИП Селлер А (447)' FROM t
  UNION ALL
  SELECT '22222222-0000-4000-8000-00000000000b'::uuid, tenant_id, 'ИП Селлер Б (447)' FROM t
  ON CONFLICT (id) DO NOTHING
  RETURNING id
)
SELECT count(*) FROM s;

INSERT INTO fbs_supplies (id, tenant_id, seller_id, warehouse_id, marketplace, wb_supply_id, external_supply_id, name, display_number, source, status, delivery_type, delivered_at)
SELECT '33333333-0000-4000-8000-0000000000a1'::uuid, id, '22222222-0000-4000-8000-00000000000a'::uuid, '11111111-0000-4000-8000-000000000001'::uuid, 'wb', 'WB-GI-447001', 'WB-GI-447001', 'Поставка A-1', 'WB-GI-447001', 'wms', 'in_delivery', 'warehouse_sc', '2026-09-10 00:30:00+03'::timestamptz FROM tenants WHERE slug='wms-test'
UNION ALL
SELECT '33333333-0000-4000-8000-0000000000a2'::uuid, id, '22222222-0000-4000-8000-00000000000a'::uuid, '11111111-0000-4000-8000-000000000001'::uuid, 'wb', 'WB-GI-447002', 'WB-GI-447002', 'Поставка A-2', 'WB-GI-447002', 'wms', 'done', 'warehouse_sc', '2026-09-12 09:00:00+03'::timestamptz FROM tenants WHERE slug='wms-test'
UNION ALL
SELECT '33333333-0000-4000-8000-0000000000a3'::uuid, id, '22222222-0000-4000-8000-00000000000a'::uuid, '11111111-0000-4000-8000-000000000001'::uuid, 'wb', 'WB-GI-447003', 'WB-GI-447003', 'Поставка A-3', 'WB-GI-447003', 'wms', 'packed', 'warehouse_sc', NULL::timestamptz FROM tenants WHERE slug='wms-test'
UNION ALL
SELECT '33333333-0000-4000-8000-0000000000a4'::uuid, id, '22222222-0000-4000-8000-00000000000a'::uuid, '11111111-0000-4000-8000-000000000001'::uuid, 'wb', 'WB-GI-447004', 'WB-GI-447004', 'Поставка A-4', 'WB-GI-447004', 'wb', 'done', 'warehouse_sc', NULL::timestamptz FROM tenants WHERE slug='wms-test'
UNION ALL
SELECT '33333333-0000-4000-8000-0000000000a5'::uuid, id, '22222222-0000-4000-8000-00000000000a'::uuid, '11111111-0000-4000-8000-000000000001'::uuid, 'wb', 'WB-GI-447005', 'WB-GI-447005', 'Поставка A-5', 'WB-GI-447005', 'wms', 'in_delivery', 'warehouse_sc', '2026-09-13 23:30:00+03'::timestamptz FROM tenants WHERE slug='wms-test'
UNION ALL
SELECT '33333333-0000-4000-8000-0000000000b1'::uuid, id, '22222222-0000-4000-8000-00000000000b'::uuid, '11111111-0000-4000-8000-000000000001'::uuid, 'ozon', NULL::varchar, 'OZ-447101', 'Поставка B-1', 'OZ-447101', 'wms', 'in_delivery', 'warehouse_sc', '2026-09-11 15:00:00+03'::timestamptz FROM tenants WHERE slug='wms-test'
ON CONFLICT (id) DO NOTHING;

INSERT INTO fbs_orders (id, tenant_id, seller_id, warehouse_id, supply_id, marketplace, wb_order_id, external_order_id, status, created_at_wb, deadline_at, mapping_status, reserve_status)
SELECT '44444444-0000-4000-8000-000000000001'::uuid, id, '22222222-0000-4000-8000-00000000000a'::uuid, '11111111-0000-4000-8000-000000000001'::uuid, '33333333-0000-4000-8000-0000000000a1'::uuid, 'wb', 447000001, NULL::varchar, 'in_delivery', '2026-09-09 10:00+03'::timestamptz, '2026-09-11 10:00+03'::timestamptz, 'unmapped', 'none' FROM tenants WHERE slug='wms-test'
UNION ALL
SELECT '44444444-0000-4000-8000-000000000002'::uuid, id, '22222222-0000-4000-8000-00000000000a'::uuid, '11111111-0000-4000-8000-000000000001'::uuid, '33333333-0000-4000-8000-0000000000a1'::uuid, 'wb', 447000002, NULL::varchar, 'in_delivery', '2026-09-09 10:00+03'::timestamptz, '2026-09-11 10:00+03'::timestamptz, 'unmapped', 'none' FROM tenants WHERE slug='wms-test'
UNION ALL
SELECT '44444444-0000-4000-8000-000000000003'::uuid, id, '22222222-0000-4000-8000-00000000000a'::uuid, '11111111-0000-4000-8000-000000000001'::uuid, '33333333-0000-4000-8000-0000000000a2'::uuid, 'wb', 447000003, NULL::varchar, 'done', '2026-09-11 10:00+03'::timestamptz, '2026-09-13 10:00+03'::timestamptz, 'unmapped', 'none' FROM tenants WHERE slug='wms-test'
UNION ALL
SELECT '44444444-0000-4000-8000-000000000004'::uuid, id, '22222222-0000-4000-8000-00000000000a'::uuid, '11111111-0000-4000-8000-000000000001'::uuid, '33333333-0000-4000-8000-0000000000a3'::uuid, 'wb', 447000004, NULL::varchar, 'packed', '2026-09-12 10:00+03'::timestamptz, '2026-09-14 10:00+03'::timestamptz, 'unmapped', 'none' FROM tenants WHERE slug='wms-test'
UNION ALL
SELECT '44444444-0000-4000-8000-000000000005'::uuid, id, '22222222-0000-4000-8000-00000000000a'::uuid, '11111111-0000-4000-8000-000000000001'::uuid, '33333333-0000-4000-8000-0000000000a5'::uuid, 'wb', 447000005, NULL::varchar, 'in_delivery', '2026-09-13 10:00+03'::timestamptz, '2026-09-15 10:00+03'::timestamptz, 'unmapped', 'none' FROM tenants WHERE slug='wms-test'
UNION ALL
SELECT '44444444-0000-4000-8000-000000000101'::uuid, id, '22222222-0000-4000-8000-00000000000b'::uuid, '11111111-0000-4000-8000-000000000001'::uuid, '33333333-0000-4000-8000-0000000000b1'::uuid, 'ozon', -447000101, 'OZ-447101-0001-1', 'in_delivery', '2026-09-10 10:00+03'::timestamptz, '2026-09-12 10:00+03'::timestamptz, 'unmapped', 'none' FROM tenants WHERE slug='wms-test'
ON CONFLICT (id) DO NOTHING;

-- Короба: каждой строке fbs_packing_boxes нужен свой warehouse_box.
INSERT INTO warehouse_boxes (id, tenant_id, warehouse_id, internal_barcode)
SELECT ('55555555-0000-4000-8000-0000000000' || lpad(n::text, 2, '0'))::uuid, id, '11111111-0000-4000-8000-000000000001'::uuid, 'FBS-447-' || lpad(n::text, 3, '0')
FROM tenants, generate_series(1, 8) AS n WHERE slug='wms-test'
ON CONFLICT (id) DO NOTHING;

INSERT INTO fbs_packing_boxes (id, tenant_id, supply_id, warehouse_box_id, box_number, created_without_distribution)
SELECT ('66666666-0000-4000-8000-0000000000' || lpad(n::text, 2, '0'))::uuid, id,
       CASE WHEN n <= 3 THEN '33333333-0000-4000-8000-0000000000a1'::uuid
            WHEN n = 4 THEN '33333333-0000-4000-8000-0000000000a2'::uuid
            WHEN n <= 6 THEN '33333333-0000-4000-8000-0000000000a3'::uuid
            ELSE '33333333-0000-4000-8000-0000000000b1'::uuid END,
       ('55555555-0000-4000-8000-0000000000' || lpad(n::text, 2, '0'))::uuid,
       CASE WHEN n <= 3 THEN n WHEN n = 4 THEN 1 WHEN n <= 6 THEN n - 4 ELSE n - 6 END,
       false
FROM tenants, generate_series(1, 8) AS n WHERE slug='wms-test'
ON CONFLICT (id) DO NOTHING;

COMMIT;
