-- WMS-688: owner-authorized, one-supply WMS-only repair, 2026-10-07.
-- WB read immediately before execution: done=false, order-ids=[5966484291].
\set ON_ERROR_STOP on
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '20s';
DO $$
DECLARE
  target uuid;
  o fbs_orders%ROWTYPE;
  affected integer;
BEGIN
  SELECT * INTO STRICT o FROM fbs_orders
    WHERE id='1d58fe73-df92-4847-be1e-720cffec5a59' FOR UPDATE;
  IF o.tenant_id <> 'd6e1ad21-8afa-4acf-8d0b-907b9f2adcfe'::uuid
     OR o.seller_id <> '0b8da5d8-f43a-42f5-a2ec-43173ea844bd'::uuid
     OR o.marketplace <> 'wb' OR o.wb_order_id <> 5966484291
     OR o.wb_supply_id IS DISTINCT FROM 'WB-GI-288973611'
     OR o.warehouse_id IS DISTINCT FROM '23356e4a-afb7-4149-9060-2215ba7f6d99'::uuid
     OR o.wb_warehouse_id IS DISTINCT FROM 1690194
  THEN RAISE EXCEPTION 'Order identity/scope changed'; END IF;
  SELECT id INTO target FROM fbs_supplies
    WHERE tenant_id=o.tenant_id AND seller_id=o.seller_id
      AND marketplace='wb' AND wb_supply_id=o.wb_supply_id FOR UPDATE;
  IF o.supply_id IS NOT NULL THEN
    IF target IS NOT NULL AND o.supply_id=target THEN
      RAISE NOTICE 'Already repaired: %', target; RETURN;
    END IF;
    RAISE EXCEPTION 'Order already belongs to another supply';
  END IF;
  IF o.status <> 'external_processing' OR o.supplier_status <> 'confirm'
    OR o.wb_status <> 'waiting' THEN
    RAISE EXCEPTION 'Order state changed'; END IF;
  IF EXISTS (SELECT 1 FROM fbs_order_picks WHERE fbs_order_id=o.id)
    OR EXISTS (SELECT 1 FROM fbs_packaging_fulfillments WHERE fbs_order_id=o.id)
    OR EXISTS (SELECT 1 FROM fbs_packing_box_items WHERE fbs_order_id=o.id)
  THEN RAISE EXCEPTION 'Order has physical workflow traces'; END IF;
  IF target IS NOT NULL THEN RAISE EXCEPTION 'Supply appeared; re-evaluate'; END IF;
  IF NOT EXISTS (SELECT 1 FROM fbs_warehouse_bindings
    WHERE tenant_id=o.tenant_id AND seller_id=o.seller_id AND marketplace='wb'
      AND wb_warehouse_id=o.wb_warehouse_id AND wms_warehouse_id=o.warehouse_id
      AND is_active AND served)
  THEN RAISE EXCEPTION 'Warehouse binding changed'; END IF;
  target := gen_random_uuid();
  INSERT INTO fbs_supplies (id,tenant_id,seller_id,warehouse_id,marketplace,
    external_supply_id,wb_supply_id,name,source,status,delivery_type,cargo_type,
    wb_office_id,last_wb_sync_at)
  VALUES (target,o.tenant_id,o.seller_id,o.warehouse_id,'wb',o.wb_supply_id,
    o.wb_supply_id,'Поставка от 06.10.2026 разбор','wb','assembling',
    'warehouse_sc',o.cargo_type,o.wb_office_id,now());
  UPDATE fbs_orders SET supply_id=target,status='assembling',updated_at=now()
    WHERE id=o.id AND supply_id IS NULL;
  GET DIAGNOSTICS affected = ROW_COUNT;
  IF affected <> 1 THEN RAISE EXCEPTION 'Unexpected affected orders: %',affected; END IF;
  INSERT INTO document_event (id,tenant_id,document_type,document_id,event_type,
    source,payload_json,idempotency_key)
  VALUES (gen_random_uuid(),o.tenant_id,'fbs_supply',target,'wb_supply_recovered',
    'system',jsonb_build_object('task','WMS-688','wb_supply_id',o.wb_supply_id,
      'wb_order_ids',jsonb_build_array(o.wb_order_id),'order_id',o.id,
      'previous_status',o.status,'previous_supply_id',o.supply_id,
      'authorization','Direct owner request in Codex: recover missing Vitalik WB supply',
      'external_mutations',false,'stock_mutations',false),
    'WMS-688:recover:WB-GI-288973611');
  RAISE NOTICE 'Recovered local supply %',target;
END $$;
COMMIT;
SELECT s.id,s.wb_supply_id,s.name,s.status,s.source,s.warehouse_id,
  count(o.id) AS orders FROM fbs_supplies s
  LEFT JOIN fbs_orders o ON o.supply_id=s.id
  WHERE s.tenant_id='d6e1ad21-8afa-4acf-8d0b-907b9f2adcfe'
    AND s.seller_id='0b8da5d8-f43a-42f5-a2ec-43173ea844bd'
    AND s.wb_supply_id='WB-GI-288973611' GROUP BY s.id;
