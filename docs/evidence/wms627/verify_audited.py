"""Independent read-only stock/ledger and live WB publication readback."""
import asyncio,json,sys,uuid
from collections import defaultdict
import httpx
from sqlalchemy import select,text
from app.db.session import SessionLocal
from app.models.fbs_warehouse_binding import FbsWarehouseBinding
from app.models.product import Product
from app.services.fbs_stock_rule_service import publish_amounts_for_binding
from app.services.wildberries_credentials_service import get_decrypted_marketplace_token
from app.services.wildberries_client import fetch_marketplace_stocks
async def main():
 targets=json.loads(sys.argv[1]);ids=[uuid.UUID(r['order_id']) for r in targets]
 async with SessionLocal() as s:
  await s.execute(text('SET TRANSACTION READ ONLY'))
  rows=[dict(r) for r in (await s.execute(text('SELECT t.name tenant,count(*) orders,sum(m.quantity_delta) delta FROM fbs_shipment_reversal_ledger l JOIN inventory_movements m ON m.id=l.shipment_movement_id JOIN tenants t ON t.id=l.tenant_id WHERE l.fbs_order_id=ANY(:ids) GROUP BY 1'),{'ids':ids})).mappings()]
  assert sum(r['orders'] for r in rows)==35 and sum(r['delta'] for r in rows)==-35
  print(json.dumps({'independent_ledger_readback':rows},ensure_ascii=False),flush=True)
  products=list((await s.scalars(select(Product).where(Product.id.in_([uuid.UUID(r['product_id']) for r in targets])))).all())
  by_seller=defaultdict(list)
  for p in products:by_seller[(p.tenant_id,p.seller_id)].append(p)
  async with httpx.AsyncClient(timeout=30) as c:
   for (tid,sid),ps in by_seller.items():
    binds=list((await s.scalars(select(FbsWarehouseBinding).where(FbsWarehouseBinding.tenant_id==tid,FbsWarehouseBinding.seller_id==sid,FbsWarehouseBinding.marketplace=='wb',FbsWarehouseBinding.is_active.is_(True),FbsWarehouseBinding.stock_sync_enabled.is_(True)))).all())
    for bind in binds:
     amounts=await publish_amounts_for_binding(s,bind,ps)
     keyed={int(p.wb_chrt_id):(p,amounts[p.id]) for p in ps if p.id in amounts and p.wb_chrt_id}
     if not keyed:continue
     token=await get_decrypted_marketplace_token(s,tid,sid)
     remote=await fetch_marketplace_stocks(c,api_token=token,warehouse_id=bind.wb_warehouse_id,chrt_ids=list(keyed),marketplace_api_base='https://marketplace-api.wildberries.ru')
     actual={r.chrt_id:r.amount for r in remote}
     mismatch=[{'product_id':str(p.id),'sku':p.sku_code,'expected':n,'wb':actual.get(k)} for k,(p,n) in keyed.items() if actual.get(k,0)!=n]
     print(json.dumps({'tenant_id':str(tid),'seller_id':str(sid),'warehouse':bind.wb_warehouse_id,'checked':len(keyed),'expected':sum(n for p,n in keyed.values()),'wb':sum(actual.values()),'mismatches':mismatch},ensure_ascii=False),flush=True)
  await s.rollback()
asyncio.run(main())
