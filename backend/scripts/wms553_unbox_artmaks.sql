-- WMS-553: approved one-off reset of ArtMaks intake #000007 only.
-- Execute in one transaction. The strict preconditions reject a second run.
DO $$
DECLARE
  req constant uuid := 'f140d4ca-cf60-402e-90cd-7fa9d8815f9d';
  tenant constant uuid := '82b36645-8662-497f-9631-a0743994632c';
  warehouse constant uuid := '5740eda2-b353-4c98-9755-0f2df4e862bc';
  sorting uuid;
BEGIN
  SET LOCAL lock_timeout = '5s';
  SET LOCAL statement_timeout = '20s';
  PERFORM id FROM inbound_intake_requests WHERE id=req FOR UPDATE;
  IF NOT EXISTS (SELECT 1 FROM inbound_intake_requests
      WHERE id=req AND tenant_id=tenant AND warehouse_id=warehouse AND status='sorting') THEN
    RAISE EXCEPTION 'Wrong request scope/status';
  END IF;
  SELECT id INTO STRICT sorting FROM storage_locations
    WHERE tenant_id=tenant AND warehouse_id=warehouse AND code='__SORTING__' AND deleted_at IS NULL;
  PERFORM p.id FROM products p JOIN inbound_intake_lines l ON l.product_id=p.id
    WHERE l.request_id=req ORDER BY p.id FOR UPDATE OF p;
  PERFORM id FROM inbound_intake_boxes WHERE request_id=req ORDER BY id FOR UPDATE;
  PERFORM l.id FROM inbound_intake_box_lines l JOIN inbound_intake_boxes b ON b.id=l.box_id
    WHERE b.request_id=req ORDER BY l.id FOR UPDATE OF l;
  PERFORM ib.id FROM inventory_balances ib JOIN inbound_intake_lines l ON l.product_id=ib.product_id
    WHERE l.request_id=req AND ib.tenant_id=tenant ORDER BY ib.id FOR UPDATE OF ib;
  IF (SELECT count(*) FROM inbound_intake_boxes WHERE request_id=req) <> 60
     OR EXISTS (SELECT 1 FROM inbound_intake_boxes WHERE request_id=req
                AND (tenant_id<>tenant OR storage_location_id IS DISTINCT FROM sorting))
     OR (SELECT count(*) FROM inbound_intake_lines WHERE request_id=req) <> 321
     OR (SELECT sum(actual_qty) FROM inbound_intake_lines WHERE request_id=req) <> 4139
     OR EXISTS (SELECT 1 FROM inbound_intake_lines WHERE request_id=req
                AND (posted_qty<>0 OR defective_qty<>0))
     OR EXISTS (SELECT 1 FROM inbound_intake_distribution_lines WHERE request_id=req) THEN
    RAISE EXCEPTION 'Intake changed since preflight';
  END IF;
  CREATE TEMP TABLE wms553_source ON COMMIT DROP AS
    SELECT ib.*, l.id AS intake_line_id, p.seller_id, gen_random_uuid() AS movement_group
    FROM inventory_balances ib
    JOIN inbound_intake_boxes b ON b.id=ib.container_id AND ib.container_kind='box'
    JOIN inbound_intake_lines l ON l.request_id=b.request_id AND l.product_id=ib.product_id
    JOIN products p ON p.id=ib.product_id
    WHERE b.request_id=req AND ib.tenant_id=tenant AND ib.quantity>0;
  IF (SELECT count(*) FROM wms553_source) <> 323
     OR (SELECT sum(quantity) FROM wms553_source) <> 4139
     OR EXISTS (SELECT 1 FROM wms553_source WHERE storage_location_id<>sorting
                OR quantity_unpacked<>quantity OR quantity_packed<>0)
     OR (SELECT count(*) FROM inbound_intake_box_lines l
         JOIN inbound_intake_boxes b ON b.id=l.box_id WHERE b.request_id=req) <> 323
     OR EXISTS (SELECT 1 FROM inbound_intake_box_lines l
         JOIN inbound_intake_boxes b ON b.id=l.box_id
         LEFT JOIN wms553_source s ON s.container_id=l.box_id AND s.product_id=l.product_id
         WHERE b.request_id=req AND (s.id IS NULL OR l.quantity<>s.quantity OR l.posted_qty<>0))
     OR EXISTS (SELECT 1 FROM inbound_intake_lines l
         LEFT JOIN (SELECT product_id,sum(quantity) qty FROM wms553_source GROUP BY product_id) s
         ON s.product_id=l.product_id WHERE l.request_id=req AND s.qty IS DISTINCT FROM l.actual_qty) THEN
    RAISE EXCEPTION 'Box contents and physical balances do not match';
  END IF;
  CREATE TEMP TABLE wms553_totals ON COMMIT DROP AS
    SELECT ib.product_id,sum(ib.quantity) qty,sum(ib.quantity_unpacked) unpacked,sum(ib.quantity_packed) packed
    FROM inventory_balances ib WHERE ib.tenant_id=tenant
      AND ib.product_id IN (SELECT product_id FROM wms553_source) GROUP BY ib.product_id;
  INSERT INTO inventory_movements
    (id,tenant_id,product_id,seller_id,storage_location_id,warehouse_id,quantity_delta,
     movement_type,transfer_group_id,container_kind,container_id,inbound_intake_line_id,reporting_dimensions_legacy)
    SELECT gen_random_uuid(),tenant,product_id,seller_id,sorting,warehouse,-quantity,
      'container_reattach',movement_group,'box',container_id,intake_line_id,false FROM wms553_source
    UNION ALL
    SELECT gen_random_uuid(),tenant,product_id,seller_id,sorting,warehouse,quantity,
      'container_reattach',movement_group,NULL,NULL,intake_line_id,false FROM wms553_source;
  INSERT INTO inventory_balances
    (id,tenant_id,storage_location_id,product_id,container_kind,container_id,quantity,quantity_unpacked,quantity_packed)
    SELECT gen_random_uuid(),tenant,sorting,product_id,NULL,NULL,sum(quantity),sum(quantity_unpacked),sum(quantity_packed)
    FROM wms553_source GROUP BY product_id
    ON CONFLICT (storage_location_id,product_id,(coalesce(container_id,'00000000-0000-0000-0000-000000000000'::uuid)))
    DO UPDATE SET quantity=inventory_balances.quantity+excluded.quantity,
      quantity_unpacked=inventory_balances.quantity_unpacked+excluded.quantity_unpacked,
      quantity_packed=inventory_balances.quantity_packed+excluded.quantity_packed,updated_at=now();
  UPDATE inventory_balances SET quantity=0,quantity_unpacked=0,quantity_packed=0,updated_at=now()
    WHERE id IN (SELECT id FROM wms553_source);
  DELETE FROM inbound_intake_box_lines WHERE box_id IN
    (SELECT id FROM inbound_intake_boxes WHERE request_id=req);
  IF EXISTS (SELECT 1 FROM wms553_totals old
      JOIN (SELECT product_id,sum(quantity) qty,sum(quantity_unpacked) unpacked,sum(quantity_packed) packed
            FROM inventory_balances WHERE tenant_id=tenant GROUP BY product_id) new USING(product_id)
      WHERE old.qty<>new.qty OR old.unpacked<>new.unpacked OR old.packed<>new.packed)
     OR EXISTS (SELECT 1 FROM inventory_balances ib JOIN inbound_intake_boxes b ON b.id=ib.container_id
                WHERE b.request_id=req AND ib.container_kind='box' AND ib.quantity<>0) THEN
    RAISE EXCEPTION 'Post-check failed';
  END IF;
END $$;
