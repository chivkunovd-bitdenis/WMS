BEGIN READ ONLY;
SET LOCAL statement_timeout='5s'; SET LOCAL lock_timeout='1s';
WITH selected AS (
 SELECT p.id product_id,c.id code_id,octet_length(c.label_artifact_pdf) bytes
 FROM products p JOIN marking_pool_products l ON l.product_id=p.id AND l.tenant_id=p.tenant_id
 JOIN marking_codes c ON c.pool_id=l.pool_id AND c.tenant_id=p.tenant_id AND c.seller_id=p.seller_id AND c.source='pool' AND (c.product_id IS NULL OR c.product_id=p.id)
 UNION ALL
 SELECT p.id,c.id,octet_length(c.label_artifact_pdf)
 FROM products p JOIN marking_codes c ON c.product_id=p.id AND c.tenant_id=p.tenant_id AND c.seller_id=p.seller_id AND c.source='pool'
 WHERE NOT EXISTS(SELECT 1 FROM marking_pool_products l WHERE l.product_id=p.id AND l.tenant_id=p.tenant_id)
), grouped AS (SELECT product_id,count(*) n,sum(bytes) bytes FROM selected GROUP BY product_id)
SELECT count(*) products_with_codes,max(n) largest_list_codes,max(bytes) largest_list_pdf_bytes FROM grouped;
ROLLBACK;
