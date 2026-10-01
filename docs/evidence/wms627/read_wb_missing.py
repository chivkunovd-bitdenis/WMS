"""Live WB read-only supply details and order membership for audit candidates."""
import asyncio,json
import httpx
from sqlalchemy import text
from app.db.session import SessionLocal
from app.services.wildberries_credentials_service import get_decrypted_marketplace_token
from app.services.wildberries_fbs_client import fetch_marketplace_supply_order_ids

async def main():
 async with SessionLocal() as s:
  await s.execute(text('SET TRANSACTION READ ONLY'))
  rows=[dict(r) for r in (await s.execute(text("""SELECT DISTINCT s.id,s.tenant_id,s.seller_id,s.wb_supply_id,s.source FROM fbs_supplies s JOIN fbs_orders o ON o.supply_id=s.id LEFT JOIN fbs_shipment_reversal_ledger l ON l.fbs_order_id=o.id WHERE s.marketplace='wb' AND s.status IN ('done','in_delivery') AND o.product_id IS NOT NULL AND o.status<>'cancelled' AND l.shipment_movement_id IS NULL AND l.reversed_at IS NULL ORDER BY s.source DESC,s.wb_supply_id DESC"""))).mappings()]
  sellers={}
  for row in rows:sellers.setdefault((row['tenant_id'],row['seller_id']),[]).append(row)
  tokens={key:await get_decrypted_marketplace_token(s,*key) for key in sellers}
  await s.rollback()
 sem=asyncio.Semaphore(4)
 async with httpx.AsyncClient(timeout=25) as c:
  async def seller(key,group):
   async with sem:
    for row in group:
     result={k:str(v) for k,v in row.items()}
     try:
      r=await c.get('https://marketplace-api.wildberries.ru/api/v3/supplies/'+row['wb_supply_id'],headers={'Authorization':tokens[key] or ''})
      result['http_status']=r.status_code
      if r.status_code==200:
       data=r.json();result.update({k:data.get(k) for k in ['done','createdAt','closedAt','scanDt']})
       if data.get('done') is True:
        result['order_ids']=await fetch_marketplace_supply_order_ids(c,api_token=tokens[key],supply_id=row['wb_supply_id'],marketplace_api_base='https://marketplace-api.wildberries.ru')
     except Exception as exc:result['error']=type(exc).__name__
     print(json.dumps(result,ensure_ascii=False,default=str),flush=True)
     await asyncio.sleep(.5)
  await asyncio.gather(*(seller(k,g) for k,g in sellers.items()))
asyncio.run(main())
