-- WMS-414 lane 1: fresh production facts for historical/configuration tasks.
-- Execute each SELECT in its own transaction with:
--   BEGIN TRANSACTION READ ONLY;
--   SET LOCAL statement_timeout = '10s';
--   SET LOCAL lock_timeout = '1s';
-- and ROLLBACK afterwards. No FOR UPDATE, service calls or CLI dry-runs.
-- Scope is the known tenant "Империя ФФ" only; results are aggregates or the
-- already-canonical WMS-048 order id. No names, contacts, credentials or KIZ.

-- A. WMS-022 / WMS-023 / WMS-024: current billing switch, service switches,
-- and tariff units/ranges for FBS, packing, inbound and marketplace outbound.
SELECT
  t.id AS tenant_id,
  t.billing_enabled_from,
  s.service_code,
  s.enabled AS service_enabled,
  count(v.id) AS tariff_versions,
  count(v.id) FILTER (WHERE v.enabled) AS enabled_versions,
  array_agg(DISTINCT v.unit) FILTER (WHERE v.id IS NOT NULL) AS units,
  min(v.valid_from_at) AS first_valid_from,
  max(v.valid_to_at) AS last_valid_to
FROM tenants t
LEFT JOIN billing_tariff_matrix_configs c ON c.tenant_id = t.id
LEFT JOIN billing_tariff_service_states s
  ON s.config_id = c.id
 AND s.service_code IN ('fbs_order','packing','inbound','marketplace_outbound')
LEFT JOIN billing_tariff_versions_v2 v
  ON v.tenant_id = t.id
 AND v.service_code = s.service_code
WHERE t.id = '7b98a8aa-c03c-4649-9677-a645be45c622'
GROUP BY t.id, t.billing_enabled_from, s.service_code, s.enabled
ORDER BY s.service_code;

-- B. WMS-013 / WMS-021 / WMS-025: current confirmed-handover coverage.
-- A WB row is considered proven only by delivered supply or confirmed
-- supply_deliver operation; status alone is deliberately insufficient.
WITH scoped_orders AS (
  SELECT o.id, o.tenant_id, o.seller_id, o.marketplace,
         coalesce(u.delivered_at, op.confirmed_at) AS handover_at
  FROM fbs_orders o
  LEFT JOIN fbs_supplies u
    ON u.id = o.supply_id
   AND u.tenant_id = o.tenant_id
  LEFT JOIN LATERAL (
    SELECT w.confirmed_at
    FROM fbs_wb_operations w
    WHERE w.tenant_id = o.tenant_id
      AND w.seller_id = o.seller_id
      AND w.local_entity_type = 'fbs_supply'
      AND w.local_entity_id = o.supply_id
      AND w.operation_kind = 'supply_deliver'
      AND w.state = 'confirmed'
      AND w.confirmed_at IS NOT NULL
    ORDER BY w.confirmed_at
    LIMIT 1
  ) op ON true
  WHERE o.tenant_id = '7b98a8aa-c03c-4649-9677-a645be45c622'
), proven AS (
  SELECT * FROM scoped_orders
  WHERE handover_at IS NOT NULL
), facts AS (
  SELECT DISTINCT ON (f.document_id)
         f.document_id, f.id, f.occurred_at, f.item_quantity
  FROM operation_facts f
  WHERE f.tenant_id = '7b98a8aa-c03c-4649-9677-a645be45c622'
    AND f.document_type = 'fbs_order'
    AND f.operation_code = 'fbs_order'
  ORDER BY f.document_id, f.created_at
)
SELECT
  p.marketplace,
  count(*) AS proven_orders,
  count(f.id) AS with_fact,
  count(*) FILTER (WHERE f.id IS NULL) AS missing_fact,
  count(*) FILTER (WHERE abs(extract(epoch FROM (f.occurred_at-p.handover_at))) > 60)
    AS fact_time_diff_over_60s,
  count(*) FILTER (WHERE EXISTS (
    SELECT 1 FROM billing_ledger_entries b
    WHERE b.tenant_id = p.tenant_id
      AND b.source_type = 'fbs_order'
      AND b.source_id = p.id
      AND b.service_code = 'fbs_order'
      AND b.entry_type = 'charge'
  )) AS with_fbs_charge,
  count(*) FILTER (WHERE EXISTS (
    SELECT 1 FROM billing_ledger_entries b
    WHERE b.tenant_id = p.tenant_id
      AND b.source_type = 'fbs_order'
      AND b.source_id = p.id
      AND b.service_code = 'packing'
      AND b.entry_type = 'charge'
  )) AS with_packing_charge,
  min(p.handover_at) AS first_handover,
  max(p.handover_at) AS last_handover
FROM proven p
LEFT JOIN facts f ON f.document_id = p.id
GROUP BY p.marketplace
ORDER BY p.marketplace;

-- C. WMS-025: all operation facts in the historical August/September window,
-- split by service and whether a charge exists. This shows what a new backfill
-- would still have to create; it does not calculate money or mutate data.
SELECT
  f.billable_service_code,
  count(*) AS operation_facts,
  sum(f.item_quantity) AS item_quantity,
  count(*) FILTER (WHERE EXISTS (
    SELECT 1 FROM billing_ledger_entries b
    WHERE b.tenant_id = f.tenant_id
      AND b.source_type = f.document_type
      AND b.source_id = f.document_id
      AND b.service_code = f.billable_service_code
      AND b.entry_type = 'charge'
  )) AS charged_facts,
  count(*) FILTER (WHERE NOT EXISTS (
    SELECT 1 FROM billing_ledger_entries b
    WHERE b.tenant_id = f.tenant_id
      AND b.source_type = f.document_type
      AND b.source_id = f.document_id
      AND b.service_code = f.billable_service_code
      AND b.entry_type = 'charge'
  )) AS uncharged_facts
FROM operation_facts f
WHERE f.tenant_id = '7b98a8aa-c03c-4649-9677-a645be45c622'
  AND f.reversal_of_id IS NULL
  AND f.billable_service_code IN ('inbound','marketplace_outbound','return','fbs_order')
  AND f.occurred_at >= timestamptz '2026-08-01 00:00:00+03'
  AND f.occurred_at <  timestamptz '2026-09-10 00:00:00+03'
GROUP BY f.billable_service_code
ORDER BY f.billable_service_code;

-- D. WMS-028: completed/posted inbound documents whose header/lines still show
-- planned quantity but zero actual quantity; compare to recorded inbound facts.
WITH line_totals AS (
  SELECT request_id,
         sum(expected_qty) AS expected_qty,
         sum(coalesce(actual_qty,0)) AS actual_qty,
         sum(posted_qty) AS posted_qty
  FROM inbound_intake_lines
  GROUP BY request_id
), fact_totals AS (
  SELECT tenant_id, document_id,
         count(*) AS operation_facts,
         sum(item_quantity) AS fact_items
  FROM operation_facts
  WHERE document_type = 'inbound'
    AND operation_code = 'inbound_completed'
  GROUP BY tenant_id, document_id
)
SELECT
  r.status,
  count(*) AS documents,
  sum(l.expected_qty) AS expected_qty,
  sum(l.actual_qty) AS actual_qty,
  sum(l.posted_qty) AS posted_qty,
  sum(coalesce(f.operation_facts,0)) AS operation_facts,
  sum(coalesce(f.fact_items,0)) AS fact_items,
  min(r.created_at) AS first_created,
  max(r.created_at) AS last_created
FROM inbound_intake_requests r
JOIN line_totals l ON l.request_id = r.id
LEFT JOIN fact_totals f ON f.tenant_id = r.tenant_id AND f.document_id = r.id
WHERE r.tenant_id = '7b98a8aa-c03c-4649-9677-a645be45c622'
  AND l.expected_qty > 0
  AND l.actual_qty = 0
GROUP BY r.status
ORDER BY r.status;

-- E. WMS-016: current scope of stock held before its first recorded dimensions.
-- This only counts affected products/units; it does not decide retroactivity.
WITH first_dim AS (
  SELECT product_id, min(observed_at) AS first_observed_at
  FROM product_dimension_events
  WHERE tenant_id = '7b98a8aa-c03c-4649-9677-a645be45c622'
  GROUP BY product_id
), first_positive AS (
  SELECT product_id, min(created_at) AS first_positive_movement
  FROM inventory_movements
  WHERE tenant_id = '7b98a8aa-c03c-4649-9677-a645be45c622'
    AND quantity_delta > 0
  GROUP BY product_id
), current_stock AS (
  SELECT product_id, sum(quantity) AS quantity
  FROM inventory_balances
  WHERE tenant_id = '7b98a8aa-c03c-4649-9677-a645be45c622'
  GROUP BY product_id
)
SELECT
  count(*) FILTER (WHERE cs.quantity > 0) AS products_with_stock,
  count(*) FILTER (
    WHERE cs.quantity > 0
      AND (fd.first_observed_at IS NULL OR fp.first_positive_movement < fd.first_observed_at)
  ) AS products_stock_before_first_dimensions,
  sum(cs.quantity) FILTER (
    WHERE cs.quantity > 0
      AND (fd.first_observed_at IS NULL OR fp.first_positive_movement < fd.first_observed_at)
  ) AS current_units_in_affected_products
FROM current_stock cs
LEFT JOIN first_dim fd ON fd.product_id = cs.product_id
LEFT JOIN first_positive fp ON fp.product_id = cs.product_id;

-- F. WMS-047: fresh aggregate of shipment-ledger rows still missing their
-- movement. Same safety boundary as the 08.09 report, without seller names/IDs.
WITH candidates AS (
  SELECT l.id, l.quantity, l.tenant_id, l.product_id, l.storage_location_id,
         l.container_kind, l.container_id
  FROM fbs_shipment_reversal_ledger l
  JOIN fbs_orders o ON o.id = l.fbs_order_id AND o.tenant_id = l.tenant_id
  JOIN fbs_supplies u ON u.id = o.supply_id AND u.tenant_id = o.tenant_id
  JOIN products p ON p.id = l.product_id AND p.tenant_id = l.tenant_id
  WHERE l.tenant_id = '7b98a8aa-c03c-4649-9677-a645be45c622'
    AND u.delivered_at IS NOT NULL
    AND u.source = 'wms'
    AND o.marketplace = 'wb'
    AND o.status NOT IN ('cancelled','defect')
    AND l.reversed_at IS NULL
    AND l.shipment_movement_id IS NULL
    AND p.seller_id = o.seller_id
), exact_sources AS (
  SELECT tenant_id, product_id, storage_location_id, container_kind, container_id,
         count(*) AS candidate_rows,
         sum(quantity) AS candidate_units
  FROM candidates
  GROUP BY tenant_id, product_id, storage_location_id, container_kind, container_id
)
SELECT
  (SELECT count(*) FROM candidates) AS rows,
  (SELECT sum(quantity) FROM candidates) AS units,
  count(*) AS exact_source_groups,
  count(*) FILTER (WHERE coalesce(b.quantity,0) < s.candidate_units)
    AS insufficient_source_groups,
  sum(greatest(s.candidate_units-coalesce(b.quantity,0),0)) AS shortage_units,
  (SELECT md5(string_agg(id::text,',' ORDER BY id)) FROM candidates) AS candidate_ids_md5
FROM exact_sources s
LEFT JOIN inventory_balances b
  ON b.tenant_id = s.tenant_id
 AND b.product_id = s.product_id
 AND b.storage_location_id = s.storage_location_id
 AND b.container_kind IS NOT DISTINCT FROM s.container_kind
 AND b.container_id IS NOT DISTINCT FROM s.container_id;

-- G. WMS-048: current invariant for the already-canonical missing order only.
SELECT
  o.id AS order_id,
  o.status,
  u.source AS supply_source,
  u.delivered_at,
  ledger.ledger_rows,
  ledger.linked_shipment_movements,
  picks.active_picks,
  coalesce((SELECT sum(b.quantity) FROM inventory_balances b
            WHERE b.tenant_id=o.tenant_id AND b.product_id=o.product_id),0)
    AS current_product_balance
FROM fbs_orders o
LEFT JOIN fbs_supplies u ON u.id=o.supply_id AND u.tenant_id=o.tenant_id
LEFT JOIN LATERAL (
  SELECT count(*) AS ledger_rows,
         count(shipment_movement_id) AS linked_shipment_movements
  FROM fbs_shipment_reversal_ledger l
  WHERE l.fbs_order_id=o.id
) ledger ON true
LEFT JOIN LATERAL (
  SELECT count(*) FILTER (WHERE undone_at IS NULL) AS active_picks
  FROM fbs_order_picks p
  WHERE p.fbs_order_id=o.id
) picks ON true
WHERE o.id='15272ef2-b423-4f40-95b1-a3fd99e3c821'
GROUP BY o.id,o.status,u.source,u.delivered_at,o.tenant_id,o.product_id,
         ledger.ledger_rows,ledger.linked_shipment_movements,picks.active_picks;

-- H. WMS-028: exact current equivalent of the 07.09 audit. Only inbound
-- movements linked to their intake line participate; aggregate movements per
-- line first so multiple movement rows cannot multiply line quantities.
WITH movement_by_line AS (
  SELECT m.inbound_intake_line_id AS line_id,
         count(*) AS movement_rows,
         sum(m.quantity_delta) AS movement_qty
  FROM inventory_movements m
  WHERE m.tenant_id='7b98a8aa-c03c-4649-9677-a645be45c622'
    AND m.movement_type IN ('inbound_intake','ownership_transfer_receipt')
    AND m.inbound_intake_line_id IS NOT NULL
  GROUP BY m.inbound_intake_line_id
), linked_lines AS (
  SELECT r.id AS request_id,l.id AS line_id,r.status,
         coalesce(l.actual_qty,0) AS actual_qty,
         l.posted_qty,
         m.movement_rows,m.movement_qty
  FROM inbound_intake_lines l
  JOIN inbound_intake_requests r ON r.id=l.request_id
  JOIN movement_by_line m ON m.line_id=l.id
  WHERE r.tenant_id='7b98a8aa-c03c-4649-9677-a645be45c622'
)
SELECT count(DISTINCT request_id) AS documents,
       count(*) AS linked_lines,
       sum(movement_rows) AS movement_rows,
       sum(actual_qty) AS actual_qty,
       sum(posted_qty) AS posted_qty,
       sum(movement_qty) AS movement_qty,
       count(*) FILTER (WHERE actual_qty=0 AND movement_qty>0)
         AS positive_movement_zero_actual_lines,
       count(*) FILTER (WHERE actual_qty<>movement_qty)
         AS actual_movement_mismatch_lines
FROM linked_lines;

-- I. WMS-028 boundary: receipt-like rows that cannot be attributed through
-- inbound_intake_line_id are outside H and must be reported explicitly.
SELECT m.movement_type,
       count(*) AS movement_rows,
       sum(m.quantity_delta) AS movement_qty,
       count(*) FILTER (WHERE m.inbound_intake_line_id IS NULL) AS null_line_rows,
       sum(m.quantity_delta) FILTER (WHERE m.inbound_intake_line_id IS NULL)
         AS null_line_qty
FROM inventory_movements m
WHERE m.tenant_id='7b98a8aa-c03c-4649-9677-a645be45c622'
  AND m.movement_type IN ('inbound_intake','ownership_transfer_receipt')
GROUP BY m.movement_type
ORDER BY m.movement_type;
