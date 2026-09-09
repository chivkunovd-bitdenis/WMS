import asyncio,json,datetime
from sqlalchemy import text
from app.db.session import SessionLocal,engine
queries={'ownership_names': "SELECT s.id seller_id,s.tenant_id,s.name,\n (SELECT coalesce(sum(b.quantity),0) FROM products p JOIN inventory_balances b ON b.product_id=p.id AND b.tenant_id=p.tenant_id WHERE p.seller_id=s.id) stock_qty,\n (SELECT count(*) FROM fbs_orders o WHERE o.seller_id=s.id AND o.status='done' AND NOT EXISTS (SELECT 1 FROM fbs_shipment_reversal_ledger l WHERE l.fbs_order_id=o.id)) internal_done_without_ledger\n FROM sellers s WHERE lower(s.name) SIMILAR TO '%(бугаев|агишев|горячев)%' ORDER BY s.id", 'negative_movement_groups': "WITH target AS (SELECT p.id,p.tenant_id,p.seller_id FROM products p JOIN sellers s ON s.id=p.seller_id WHERE lower(s.name) SIMILAR TO '%(бугаев|агишев)%' AND EXISTS (SELECT 1 FROM inventory_balances b WHERE b.product_id=p.id AND b.tenant_id=p.tenant_id AND b.quantity<0))\n SELECT t.seller_id,m.movement_type,count(*) movement_rows,sum(m.quantity_delta) net_qty,min(m.created_at) first_at,max(m.created_at) last_at FROM target t JOIN inventory_movements m ON m.product_id=t.id AND m.tenant_id=t.tenant_id GROUP BY t.seller_id,m.movement_type ORDER BY 1,2", 'catalog191': "SELECT s.id seller_id,s.tenant_id,s.name,count(p.id) product_rows,\n count(p.id) FILTER(WHERE p.wb_nm_id IS NOT NULL) products_with_nm,\n count(p.id) FILTER(WHERE p.wb_nm_id IS NOT NULL AND EXISTS(SELECT 1 FROM seller_wildberries_imported_cards c WHERE c.seller_id=s.id AND c.tenant_id=s.tenant_id AND c.nm_id=p.wb_nm_id)) products_matching_stored_card,\n count(p.id) FILTER(WHERE lower(p.name) SIMILAR TO '%(ламп|удобрени)%') name_candidates,\n (SELECT count(*) FROM seller_wildberries_imported_cards c WHERE c.seller_id=s.id AND c.tenant_id=s.tenant_id) stored_cards,\n (SELECT max(c.updated_at) FROM seller_wildberries_imported_cards c WHERE c.seller_id=s.id AND c.tenant_id=s.tenant_id) latest_stored_card_at\n FROM sellers s LEFT JOIN products p ON p.seller_id=s.id AND p.tenant_id=s.tenant_id WHERE lower(s.name) LIKE '%горячкин%' GROUP BY s.id,s.tenant_id,s.name ORDER BY s.id", 'catalog191_candidates': "SELECT s.id seller_id,p.id product_id,p.name,p.wb_nm_id,\n EXISTS(SELECT 1 FROM seller_wildberries_imported_cards c WHERE c.seller_id=s.id AND c.tenant_id=s.tenant_id AND c.nm_id=p.wb_nm_id) has_stored_card,\n (SELECT coalesce(sum(b.quantity),0) FROM inventory_balances b WHERE b.product_id=p.id AND b.tenant_id=p.tenant_id) stock_qty\n FROM sellers s JOIN products p ON p.seller_id=s.id AND p.tenant_id=s.tenant_id WHERE lower(s.name) LIKE '%горячкин%' AND lower(p.name) SIMILAR TO '%(ламп|удобрени)%' ORDER BY p.id LIMIT 100"}
async def main():
 for key,query in queries.items():
  async with SessionLocal() as session:
   try:
    await session.execute(text("SET TRANSACTION READ ONLY"))
    await session.execute(text("SET LOCAL statement_timeout = '10s'"))
    await session.execute(text("SET LOCAL lock_timeout = '1s'"))
    data=(await session.execute(text(query))).mappings().all()
    print(json.dumps({"section":key,"checked_at_utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),"rows":[dict(x) for x in data]},default=str),flush=True)
   except Exception as e:
    print(json.dumps({"section":key,"error_type":type(e).__name__,"detail":str(e).split("[SQL:")[0]},default=str),flush=True)
   finally: await session.rollback()
 await engine.dispose()
asyncio.run(main())
