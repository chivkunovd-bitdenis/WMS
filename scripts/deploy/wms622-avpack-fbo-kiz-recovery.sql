\set ON_ERROR_STOP on
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '30s';
SELECT id FROM packaging_tasks WHERE id = '4fbfbbcd-e1a1-451e-86dd-84466c880836' AND tenant_id = 'd6e1ad21-8afa-4acf-8d0b-907b9f2adcfe' FOR UPDATE;
SELECT id FROM packaging_task_lines WHERE task_id = '4fbfbbcd-e1a1-451e-86dd-84466c880836' FOR UPDATE;
CREATE TEMP TABLE recovery_codes ON COMMIT DROP AS
SELECT DISTINCT m.id AS code_id, l.id AS line_id, m.product_id, m.packaging_task_line_id AS old_line_id
FROM marking_code_events e
JOIN marking_codes m ON m.id = e.code_id
JOIN packaging_task_lines l ON l.task_id = e.packaging_task_id AND l.product_id = m.product_id
WHERE e.packaging_task_id = '4fbfbbcd-e1a1-451e-86dd-84466c880836'
  AND m.tenant_id = 'd6e1ad21-8afa-4acf-8d0b-907b9f2adcfe'
  AND m.seller_id = '0b8da5d8-f43a-42f5-a2ec-43173ea844bd'
  AND e.event_type IN ('printed', 'reprinted')
  AND m.status = 'printed' AND m.label_artifact_pdf IS NOT NULL;
SELECT m.id FROM marking_codes m JOIN recovery_codes r ON r.code_id = m.id FOR UPDATE OF m;
DO $$
BEGIN
  IF (SELECT count(*) FROM recovery_codes) <> 50
     OR (SELECT count(DISTINCT code_id) FROM recovery_codes) <> 50
     OR (SELECT count(*) FROM recovery_codes WHERE old_line_id IS NULL) <> 32
     OR (SELECT count(DISTINCT line_id) FROM recovery_codes WHERE old_line_id IS NULL) <> 5
     OR EXISTS (SELECT 1 FROM recovery_codes WHERE old_line_id IS NOT NULL AND old_line_id <> line_id)
     OR EXISTS (SELECT 1 FROM marking_code_events e JOIN recovery_codes r ON r.code_id=e.code_id WHERE e.packaging_task_id IS NOT NULL AND e.packaging_task_id <> '4fbfbbcd-e1a1-451e-86dd-84466c880836')
     OR EXISTS (SELECT 1 FROM packaging_task_lines l LEFT JOIN (SELECT line_id,count(*) n FROM recovery_codes GROUP BY line_id) r ON r.line_id=l.id WHERE l.task_id='4fbfbbcd-e1a1-451e-86dd-84466c880836' AND (r.n IS NULL OR l.qty_total <> r.n OR l.qty_marking_printed NOT IN (0,r.n)))
  THEN RAISE EXCEPTION 'WMS-622 preflight mismatch; no changes applied'; END IF;
END $$;
UPDATE marking_codes m SET packaging_task_line_id=r.line_id FROM recovery_codes r WHERE m.id=r.code_id AND m.packaging_task_line_id IS NULL;
UPDATE marking_code_events e SET packaging_task_line_id=r.line_id FROM recovery_codes r WHERE e.code_id=r.code_id AND e.packaging_task_id='4fbfbbcd-e1a1-451e-86dd-84466c880836' AND e.packaging_task_line_id IS NULL;
UPDATE packaging_task_events e SET line_id=l.id FROM packaging_task_lines l WHERE e.task_id=l.task_id AND e.product_id=l.product_id AND e.task_id='4fbfbbcd-e1a1-451e-86dd-84466c880836' AND e.line_id IS NULL AND e.action='product_label_print';
UPDATE packaging_task_lines l SET qty_marking_printed=r.n FROM (SELECT line_id,count(*)::integer n FROM recovery_codes GROUP BY line_id) r WHERE l.id=r.line_id AND l.qty_marking_printed <> r.n;
DO $$
BEGIN
  IF (SELECT count(*) FROM marking_codes m JOIN recovery_codes r ON r.code_id=m.id WHERE m.packaging_task_line_id=r.line_id) <> 50
     OR (SELECT sum(qty_marking_printed) FROM packaging_task_lines WHERE task_id='4fbfbbcd-e1a1-451e-86dd-84466c880836') <> 50
  THEN RAISE EXCEPTION 'WMS-622 verification mismatch; rollback'; END IF;
END $$;
INSERT INTO document_event (id,tenant_id,document_type,document_id,event_type,source,payload_json)
VALUES ('10a33c5b-cdb2-4b31-8db2-622202610001','d6e1ad21-8afa-4acf-8d0b-907b9f2adcfe','marketplace_unload','a0b43f58-299d-4b5e-9ad1-2bb294fef98d','data_changed','system','{"reason":"WMS-622 owner-authorized recovery of deleted packaging-line links","restored_code_links":32,"total_printed_codes":50,"new_codes_issued":0,"packaging_task_id":"4fbfbbcd-e1a1-451e-86dd-84466c880836"}');
SELECT p.sku_code,l.qty_total,l.qty_marking_printed,count(m.id) AS linked_codes FROM packaging_task_lines l JOIN products p ON p.id=l.product_id LEFT JOIN marking_codes m ON m.packaging_task_line_id=l.id WHERE l.task_id='4fbfbbcd-e1a1-451e-86dd-84466c880836' GROUP BY p.sku_code,l.id ORDER BY p.sku_code;
COMMIT;
