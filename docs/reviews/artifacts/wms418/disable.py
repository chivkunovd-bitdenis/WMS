"""WMS-418. Scoped Loviana operation; execute inside production API container."""
import asyncio, collections, dataclasses, hashlib, inspect, json, uuid
from sqlalchemy import select, text
from app.db.session import SessionLocal
from app.models.product import Product
from app.models.seller import Seller
from app.models.fbs_binding_stock_pool import FbsBindingStockPool
from app.services import fbs_stock_rule_service as r
T=uuid.UUID('7b98a8aa-c03c-4649-9677-a645be45c622')
S=uuid.UUID('9819f2c6-b28e-401e-a163-6ffe9e420da6')
OWN={2046998,2088990,2157282}
def out(event,**kw): print(json.dumps({'event':event,**kw},default=str),flush=True)
def key(rule): return json.dumps(dataclasses.asdict(rule),sort_keys=True)
async def state(s):
 ps=list((await s.scalars(select(Product).where(Product.tenant_id==T,Product.seller_id==S).order_by(Product.id))).all())
 bs=await r._seller_bindings(s,T,S,publishing_only=False)
 pools=list((await s.scalars(select(FbsBindingStockPool).where(FbsBindingStockPool.tenant_id==T,FbsBindingStockPool.product_id.in_([p.id for p in ps])))).all())
 by=collections.defaultdict(dict)
 for pool in pools: by[pool.product_id][pool.binding_id]=pool
 rules={p.id:r.rule_from_product(p,by[p.id],bs) for p in ps}
 flags={str(p.id):[p.fbs_stock_sync_enabled,p.fbs_ozon_stock_sync_enabled] for p in ps}
 binds=[(str(b.id),b.marketplace,b.wb_warehouse_id,b.served,b.stock_sync_enabled) for b in bs]
 return ps,bs,rules,flags,binds
async def main():
 assert hashlib.sha256(inspect.getsource(r).encode()).hexdigest()=='c97ad9c6b169ca6fea1a20be2ffa8145d46cf7817642883d322f0520adef1764'
 groups=collections.defaultdict(list); new={}
 async with SessionLocal() as s:
  seller=await s.get(Seller,S)
  assert seller and seller.name=='Loviana' and seller.tenant_id==T
  ps,bs,rules,flags,binds=await state(s)
  assert len(ps)==158 and len(bs)==5
  assert all(b.marketplace=='wb' and bool(b.served)==(b.wb_warehouse_id in OWN) and bool(b.stock_sync_enabled)==(b.wb_warehouse_id in OWN) for b in bs)
  expected={pid:key(rule) for pid,rule in rules.items()}
  for pid,old in rules.items():
   if old.publishes('wb') or old.publishes('ozon'):
    assert old.units_mode
    off=dataclasses.replace(old,publish=False,publish_ozon=False)
    k=key(off); groups[k].append(pid); new[k]=off; expected[pid]=k
  selected={pid for ids in groups.values() for pid in ids}
  out('before',total=len(ps),selected=len(selected),bindings=binds,flags=flags,rules={str(k):dataclasses.asdict(v) for k,v in rules.items()})
  rows=[dict(x) for x in (await s.execute(text('SELECT i.product_id,i.chrt_id,b.wb_warehouse_id,i.last_confirmed_amount FROM fbs_stock_sync_items i JOIN fbs_warehouse_bindings b ON b.id=i.binding_id WHERE b.tenant_id=:t AND b.seller_id=:s AND b.served AND b.stock_sync_enabled'),{'t':T,'s':S})).mappings() if x['product_id'] in selected]
  out('manifest',items=rows)
 for index,(k,ids) in enumerate(groups.items(),1):
  async with SessionLocal() as s:
   _,_,current,_,current_binds=await state(s)
   assert current_binds==binds,'Bindings changed'
   for pid in ids:
    assert key(current[pid])==key(rules[pid]),'Concurrent rule change'
   await r.set_rule_for_products(s,T,ids,new[k])
  out('disabled',group=index,of=len(groups),count=len(ids),product_ids=ids)
 async with SessionLocal() as s:
  ps,bs,current,after_flags,after_binds=await state(s)
  assert after_binds==binds
  assert len(ps)==158 and {pid:key(v) for pid,v in current.items()}==expected
  assert all(not v.publishes('wb') and not v.publishes('ozon') for v in current.values())
  assert all(after_flags[str(p.id)]==flags[str(p.id)] for p in ps if p.id not in selected)
  out('database_verified',total=158,disabled=len(selected),enabled=0,allocations_preserved=True,bindings_preserved=True,previously_off_preserved=True)
asyncio.run(main())
