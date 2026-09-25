import asyncio
import json
import sys
from pathlib import Path
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
sys.path.insert(0,str(Path('docs/reviews/artifacts/wms444-astra-review').resolve()))
from wms444_astra_review import Base, fixture, snapshot, collect, boxes, pkg, MarketplaceUnloadBox, MarketplaceUnloadBoxLine, MarketplaceUnloadPickAllocation, InventoryBalance
URL='postgresql+psycopg_async://deniscivkunov@localhost:5432/wms444_astra_review3_20260913'
engine=create_async_engine(URL)
sf=async_sessionmaker(engine,expire_on_commit=False)

async def main():
    async with engine.begin() as c:
        assert (await c.execute(select(func.current_database()))).scalar_one()=='wms444_astra_review3_20260913'
        await c.run_sync(Base.metadata.create_all)
    async with sf() as s:
        t,w,actor,p,req,task,box,line,locs=await fixture(s,[(0,0)],total=3)
        s.add_all([MarketplaceUnloadBoxLine(box_id=box.id,product_id=p.id,quantity=3),MarketplaceUnloadPickAllocation(request_id=req.id,product_id=p.id,storage_location_id=locs[0].id,quantity=3)])
        line.qty_confirmed_packed=3;line.qty_packed_in_task=0;await s.commit()
        state=await snapshot(s,t,task,p,req)
        done=await pkg.complete_task(s,t.id,task.id,acting_user_id=actor.id)
        print(json.dumps({'case':'historical-full-ready','after':state,'earned_kopecks':done.billing_earned_kopecks}))
        assert state['confirmed']==3 and state['work']==0 and done.billing_earned_kopecks==0
    async with sf() as s:
        t,w,actor,p,req,task,box,line,locs=await fixture(s,[(0,2),(1,0)])
        second=MarketplaceUnloadBox(request_id=req.id,box_preset='60_40_40');s.add(second);await s.commit()
        await collect.collect_into_box(s,t.id,req.id,box_id=box.id,storage_location_id=locs[0].id,product_id=p.id,quantity=2,actor_user_id=actor.id)
        b=await collect.collect_into_box(s,t.id,req.id,box_id=second.id,storage_location_id=locs[1].id,product_id=p.id,quantity=1,actor_user_id=actor.id)
        await s.commit()
        await collect.remove_from_box(s,t.id,req.id,box_id=second.id,line_id=b.box_line.id,quantity=1,actor_user_id=actor.id)
        returned=(await s.scalars(select(InventoryBalance).where(InventoryBalance.product_id==p.id,InventoryBalance.quantity>0))).one()
        state_removed=await snapshot(s,t,task,p,req)
        await boxes.add_manual_qty_to_box(s,t.id,second.id,product_id=p.id,storage_location_id=returned.storage_location_id,quantity=1,actor_user_id=actor.id)
        state=await snapshot(s,t,task,p,req)
        done=await pkg.complete_task(s,t.id,task.id,acting_user_id=actor.id)
        print(json.dumps({'case':'remove-recollect-actual-returned-source','returned_to_B':returned.storage_location_id==locs[1].id,'removed':state_removed,'after':state,'earned_kopecks':done.billing_earned_kopecks}))
        assert state['confirmed']==2 and state['work']==1 and state['alloc']==[3,2] and done.billing_earned_kopecks==700
    async with sf() as s:
        t,w,actor,p,req,task,box,line,locs=await fixture(s,[(2,0)],total=3)
        s.add_all([MarketplaceUnloadBoxLine(box_id=box.id,product_id=p.id,quantity=1),MarketplaceUnloadPickAllocation(request_id=req.id,product_id=p.id,storage_location_id=locs[0].id,quantity=1)])
        line.qty_confirmed_packed=1;line.qty_packed_in_task=0;await s.commit()
        await collect.collect_into_box(s,t.id,req.id,box_id=box.id,storage_location_id=locs[0].id,product_id=p.id,quantity=2,actor_user_id=actor.id)
        await s.commit();state=await snapshot(s,t,task,p,req)
        try:
            await pkg.complete_task(s,t.id,task.id,acting_user_id=actor.id)
            completion='ok'
        except Exception as exc:
            completion=getattr(exc,'code',type(exc).__name__);await s.rollback()
        print(json.dumps({'case':'historical-partial-plus-new-unpacked','expected':{'confirmed':1,'work':2,'total':3},'after':state,'complete':completion}))
    async with sf() as s:
        t,w,actor,p,req,task,box,line,locs=await fixture(s,[(0,0),(1,0)],total=3)
        historical=MarketplaceUnloadBoxLine(box_id=box.id,product_id=p.id,quantity=2)
        s.add_all([historical,MarketplaceUnloadPickAllocation(request_id=req.id,product_id=p.id,storage_location_id=locs[0].id,quantity=2)])
        line.qty_packed_in_task=2;await s.commit()
        await collect.collect_into_box(s,t.id,req.id,box_id=box.id,storage_location_id=locs[1].id,product_id=p.id,quantity=1,actor_user_id=actor.id)
        await s.commit()
        await collect.remove_from_box(s,t.id,req.id,box_id=box.id,line_id=historical.id,quantity=3,actor_user_id=actor.id)
        alloc=(await s.execute(select(func.coalesce(func.sum(MarketplaceUnloadPickAllocation.quantity),0)).where(MarketplaceUnloadPickAllocation.request_id==req.id))).scalar_one()
        bal=(await s.execute(select(func.coalesce(func.sum(InventoryBalance.quantity),0)).where(InventoryBalance.product_id==p.id))).scalar_one()
        byloc=(await s.execute(select(InventoryBalance.storage_location_id,InventoryBalance.quantity).where(InventoryBalance.product_id==p.id))).all()
        print(json.dumps({'case':'historical-unknown-removal','expected_alloc':0,'remaining_alloc':alloc,'returned_total':bal,'return_A':next(q for l,q in byloc if l==locs[0].id),'return_B':next(q for l,q in byloc if l==locs[1].id)}))
    await engine.dispose()

asyncio.run(main())
