import asyncio,json,datetime
from sqlalchemy import text
from app.db.session import SessionLocal,engine
queries={'H': "WITH target_sellers AS (\n SELECT s.id AS seller_id,s.tenant_id,\n        CASE WHEN lower(s.name) LIKE '%комаров%' THEN 'WMS-128'\n             ELSE 'WMS-129' END AS task_id\n FROM sellers s\n WHERE lower(s.name) SIMILAR TO '%(комаров|бугаев|агишев|горячев)%'\n)\nSELECT x.task_id,x.tenant_id,x.seller_id,\n (SELECT count(*) FROM marketplace_accounts a WHERE a.seller_id=x.seller_id AND a.marketplace IN ('wb','wildberries')) AS wb_account_rows,\n (SELECT count(*) FROM fbs_warehouse_bindings b WHERE b.seller_id=x.seller_id) AS binding_rows,\n (SELECT count(*) FROM fbs_warehouse_bindings b WHERE b.seller_id=x.seller_id AND b.served) AS served_binding_rows,\n (SELECT count(*) FROM fbs_orders o WHERE o.seller_id=x.seller_id) AS order_rows,\n (SELECT count(*) FROM fbs_orders o WHERE o.seller_id=x.seller_id AND o.status='done') AS internal_done_rows,\n (SELECT coalesce(sum(ib.quantity),0) FROM products p JOIN inventory_balances ib ON ib.product_id=p.id AND ib.tenant_id=p.tenant_id WHERE p.seller_id=x.seller_id) AS stock_qty,\n (SELECT max(o.created_at_wb) FROM fbs_orders o WHERE o.seller_id=x.seller_id) AS last_order_at\nFROM target_sellers x ORDER BY x.task_id,x.tenant_id,x.seller_id", 'I': "SELECT t.id AS tenant_id,count(DISTINCT s.id) AS seller_count,\n coalesce(sum(ib.quantity),0) AS stock_qty,\n min(ib.updated_at) AS oldest_balance_update,max(ib.updated_at) AS latest_balance_update\nFROM tenants t\nLEFT JOIN sellers s ON s.tenant_id=t.id\nLEFT JOIN products p ON p.seller_id=s.id AND p.tenant_id=t.id\nLEFT JOIN inventory_balances ib ON ib.product_id=p.id AND ib.tenant_id=t.id\nWHERE lower(t.name) LIKE '%львов%'\nGROUP BY t.id"}
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
