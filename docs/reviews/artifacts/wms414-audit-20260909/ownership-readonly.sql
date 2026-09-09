-- H. WMS-128/129: bounded seller/tenant state, no credentials or account secrets.
WITH target_sellers AS (
 SELECT s.id AS seller_id,s.tenant_id,
        CASE WHEN lower(s.name) LIKE '%комаров%' THEN 'WMS-128'
             ELSE 'WMS-129' END AS task_id
 FROM sellers s
 WHERE lower(s.name) SIMILAR TO '%(комаров|бугаев|агишев|горячев)%'
)
SELECT x.task_id,x.tenant_id,x.seller_id,
 (SELECT count(*) FROM marketplace_accounts a WHERE a.seller_id=x.seller_id AND a.marketplace IN ('wb','wildberries')) AS wb_account_rows,
 (SELECT count(*) FROM fbs_warehouse_bindings b WHERE b.seller_id=x.seller_id) AS binding_rows,
 (SELECT count(*) FROM fbs_warehouse_bindings b WHERE b.seller_id=x.seller_id AND b.served) AS served_binding_rows,
 (SELECT count(*) FROM fbs_orders o WHERE o.seller_id=x.seller_id) AS order_rows,
 (SELECT count(*) FROM fbs_orders o WHERE o.seller_id=x.seller_id AND o.status='done') AS internal_done_rows,
 (SELECT coalesce(sum(ib.quantity),0) FROM products p JOIN inventory_balances ib ON ib.product_id=p.id AND ib.tenant_id=p.tenant_id WHERE p.seller_id=x.seller_id) AS stock_qty,
 (SELECT max(o.created_at_wb) FROM fbs_orders o WHERE o.seller_id=x.seller_id) AS last_order_at
FROM target_sellers x ORDER BY x.task_id,x.tenant_id,x.seller_id;
-- I. WMS-130: known tenant aggregate, does not establish ownership.
SELECT t.id AS tenant_id,count(DISTINCT s.id) AS seller_count,
 coalesce(sum(ib.quantity),0) AS stock_qty,
 min(ib.updated_at) AS oldest_balance_update,max(ib.updated_at) AS latest_balance_update
FROM tenants t
LEFT JOIN sellers s ON s.tenant_id=t.id
LEFT JOIN products p ON p.seller_id=s.id AND p.tenant_id=t.id
LEFT JOIN inventory_balances ib ON ib.product_id=p.id AND ib.tenant_id=t.id
WHERE lower(t.name) LIKE '%львов%'
GROUP BY t.id;
