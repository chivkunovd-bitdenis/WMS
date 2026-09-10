-- ownership_names
SELECT s.id seller_id,s.tenant_id,s.name,
 (SELECT coalesce(sum(b.quantity),0) FROM products p JOIN inventory_balances b ON b.product_id=p.id AND b.tenant_id=p.tenant_id WHERE p.seller_id=s.id) stock_qty,
 (SELECT count(*) FROM fbs_orders o WHERE o.seller_id=s.id AND o.status='done' AND NOT EXISTS (SELECT 1 FROM fbs_shipment_reversal_ledger l WHERE l.fbs_order_id=o.id)) internal_done_without_ledger
 FROM sellers s WHERE lower(s.name) SIMILAR TO '%(бугаев|агишев|горячев)%' ORDER BY s.id;

-- negative_movement_groups
WITH target AS (SELECT p.id,p.tenant_id,p.seller_id FROM products p JOIN sellers s ON s.id=p.seller_id WHERE lower(s.name) SIMILAR TO '%(бугаев|агишев)%' AND EXISTS (SELECT 1 FROM inventory_balances b WHERE b.product_id=p.id AND b.tenant_id=p.tenant_id AND b.quantity<0))
 SELECT t.seller_id,m.movement_type,count(*) movement_rows,sum(m.quantity_delta) net_qty,min(m.created_at) first_at,max(m.created_at) last_at FROM target t JOIN inventory_movements m ON m.product_id=t.id AND m.tenant_id=t.tenant_id GROUP BY t.seller_id,m.movement_type ORDER BY 1,2;

-- catalog191
SELECT s.id seller_id,s.tenant_id,s.name,count(p.id) product_rows,
 count(p.id) FILTER(WHERE p.wb_nm_id IS NOT NULL) products_with_nm,
 count(p.id) FILTER(WHERE p.wb_nm_id IS NOT NULL AND EXISTS(SELECT 1 FROM seller_wildberries_imported_cards c WHERE c.seller_id=s.id AND c.tenant_id=s.tenant_id AND c.nm_id=p.wb_nm_id)) products_matching_stored_card,
 count(p.id) FILTER(WHERE lower(p.name) SIMILAR TO '%(ламп|удобрени)%') name_candidates,
 (SELECT count(*) FROM seller_wildberries_imported_cards c WHERE c.seller_id=s.id AND c.tenant_id=s.tenant_id) stored_cards,
 (SELECT max(c.updated_at) FROM seller_wildberries_imported_cards c WHERE c.seller_id=s.id AND c.tenant_id=s.tenant_id) latest_stored_card_at
 FROM sellers s LEFT JOIN products p ON p.seller_id=s.id AND p.tenant_id=s.tenant_id WHERE lower(s.name) LIKE '%горячкин%' GROUP BY s.id,s.tenant_id,s.name ORDER BY s.id;

-- catalog191_candidates
SELECT s.id seller_id,p.id product_id,p.name,p.wb_nm_id,
 EXISTS(SELECT 1 FROM seller_wildberries_imported_cards c WHERE c.seller_id=s.id AND c.tenant_id=s.tenant_id AND c.nm_id=p.wb_nm_id) has_stored_card,
 (SELECT coalesce(sum(b.quantity),0) FROM inventory_balances b WHERE b.product_id=p.id AND b.tenant_id=p.tenant_id) stock_qty
 FROM sellers s JOIN products p ON p.seller_id=s.id AND p.tenant_id=s.tenant_id WHERE lower(s.name) LIKE '%горячкин%' AND lower(p.name) SIMILAR TO '%(ламп|удобрени)%' ORDER BY p.id LIMIT 100;
