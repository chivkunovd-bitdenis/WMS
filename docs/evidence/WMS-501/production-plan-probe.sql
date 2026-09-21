BEGIN READ ONLY;
SET LOCAL statement_timeout='5s';
SET LOCAL lock_timeout='1s';
SELECT count(*) AS tenant_scopes_with_products, min(n) AS smallest, max(n) AS largest, percentile_cont(0.5) WITHIN GROUP(ORDER BY n) AS median FROM (SELECT tenant_id,count(*) AS n FROM products GROUP BY tenant_id) q;
SELECT count(*) AS codes, count(label_artifact_pdf) AS codes_with_pdf, sum(octet_length(label_artifact_pdf)) AS total_pdf_bytes, max(octet_length(label_artifact_pdf)) AS largest_pdf_bytes FROM marking_codes;
SELECT max(n) AS largest_product_code_count,max(bytes) AS largest_product_pdf_bytes FROM (SELECT product_id,count(*) n,sum(octet_length(label_artifact_pdf)) bytes FROM marking_codes GROUP BY product_id) q;
EXPLAIN (ANALYZE,BUFFERS,FORMAT JSON)
SELECT p.id FROM products p
WHERE p.tenant_id=(SELECT tenant_id FROM products GROUP BY tenant_id ORDER BY count(*) DESC LIMIT 1)
AND (p.sku_code ILIKE '%WMS501-NO-SUCH-PRODUCT%' OR p.name ILIKE '%WMS501-NO-SUCH-PRODUCT%' OR p.wb_barcode ILIKE '%WMS501-NO-SUCH-PRODUCT%' OR p.wb_vendor_code ILIKE '%WMS501-NO-SUCH-PRODUCT%' OR CAST(p.wb_nm_id AS varchar) ILIKE '%WMS501-NO-SUCH-PRODUCT%' OR EXISTS(SELECT 1 FROM product_marketplace_links l WHERE l.tenant_id=p.tenant_id AND l.product_id=p.id AND l.marketplace='ozon' AND l.is_active AND (l.external_sku ILIKE '%WMS501-NO-SUCH-PRODUCT%' OR l.external_offer_id ILIKE '%WMS501-NO-SUCH-PRODUCT%' OR CAST(l.external_barcodes AS varchar) ILIKE '%"WMS501-NO-SUCH-PRODUCT"%')))
ORDER BY p.sku_code LIMIT 50;
ROLLBACK;
