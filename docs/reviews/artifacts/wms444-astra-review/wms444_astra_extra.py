import asyncio
import json
from sqlalchemy import select, func
from wms444_astra_review import sf, engine, fixture, snapshot, collect, boxes, pkg, MarketplaceUnloadBox, MarketplaceUnloadBoxLine, MarketplaceUnloadPickAllocation, InventoryBalance

async def main():
    async with sf() as s:
        t,w,actor,p,req,task,box,line,locs=await fixture(s,[(1,2)])
        await collect.record_pick_allocation(s,t.id,req.id,storage_location_id=locs[0].id,product_id=p.id,quantity=3,actor_user_id=actor.id)
        await boxes.add_manual_qty_to_box(s,t.id,box.id,product_id=p.id,storage_location_id=locs[0].id,quantity=3,actor_user_id=actor.id)
        state=await snapshot(s,t,task,p,req)
        print(json.dumps({'case':'prepick-then-box','state':state}))
        assert state['confirmed']==2 and state['work']==1 and state['alloc']==[3,2]
    async with sf() as s:
        t,w,actor,p,req,task,box,line,locs=await fixture(s,[(0,1)])
        await collect.record_pick_allocation(s,t.id,req.id,storage_location_id=locs[0].id,product_id=p.id,quantity=1,actor_user_id=actor.id)
        await s.commit()
    async def place():
        async with sf() as s:
            try:
                await boxes.add_manual_qty_to_box(s,t.id,box.id,product_id=p.id,storage_location_id=locs[0].id,quantity=1,actor_user_id=actor.id)
                return 'ok'
            except Exception as e:
                await s.rollback()
                return getattr(e,'code',type(e).__name__)
    results=await asyncio.wait_for(asyncio.gather(place(),place()),timeout=20)
    async with sf() as s:
        state=await snapshot(s,t,task,p,req)
        print(json.dumps({'case':'concurrent-placement-last-picked-unit','results':results,'state':state}))
        assert results.count('ok')==1 and state['total']==1 and state['confirmed']==1
    async with sf() as s:
        t,w,actor,p,req,task,box,line,locs=await fixture(s,[(1,2)])
        await collect.collect_into_box(s,t.id,req.id,box_id=box.id,storage_location_id=locs[0].id,product_id=p.id,quantity=3,actor_user_id=actor.id)
        await s.commit()
        await collect.rollback_all_collected_for_cancel(s,t.id,w.id,req.id,actor_user_id=actor.id)
        await s.commit()
        bal=(await s.execute(select(func.sum(InventoryBalance.quantity),func.sum(InventoryBalance.quantity_packed)).where(InventoryBalance.product_id==p.id))).one()
        print(json.dumps({'case':'cancel-mixed','balance':list(bal)}))
        assert list(bal)==[3,2]
    # Faithful post-upgrade state: source already consumed and historic ready confirmed.
    async with sf() as s:
        t,w,actor,p,req,task,box,line,locs=await fixture(s,[(0,0)],total=3)
        s.add_all([MarketplaceUnloadBoxLine(box_id=box.id,product_id=p.id,quantity=3),MarketplaceUnloadPickAllocation(request_id=req.id,product_id=p.id,storage_location_id=locs[0].id,quantity=3)])
        line.qty_confirmed_packed=3;line.qty_packed_in_task=0;await s.commit()
        state=await snapshot(s,t,task,p,req)
        done=await pkg.complete_task(s,t.id,task.id,acting_user_id=actor.id)
        print(json.dumps({'case':'historical-ready-source-consumed','after':state,'earned_kopecks':done.billing_earned_kopecks}))
    await engine.dispose()

asyncio.run(main())
