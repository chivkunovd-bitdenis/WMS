import asyncio
import json
from sqlalchemy import select
from wms444_astra_review import sf, engine, fixture, snapshot, collect, boxes, pkg, MarketplaceUnloadBoxLine, MarketplaceUnloadPickAllocation

async def main():
    async with sf() as s:
        t,w,actor,p,req,task,box,line,locs=await fixture(s,[(1,0)],total=3)
        historical=MarketplaceUnloadBoxLine(box_id=box.id,product_id=p.id,quantity=2)
        s.add_all([historical,MarketplaceUnloadPickAllocation(request_id=req.id,product_id=p.id,storage_location_id=locs[0].id,quantity=2)])
        line.qty_confirmed_packed=2;line.qty_packed_in_task=0;await s.commit()
        await collect.collect_into_box(s,t.id,req.id,box_id=box.id,storage_location_id=locs[0].id,product_id=p.id,quantity=1,actor_user_id=actor.id)
        await s.commit();before=await snapshot(s,t,task,p,req)
        await collect.remove_from_box(s,t.id,req.id,box_id=box.id,line_id=historical.id,quantity=1,actor_user_id=actor.id)
        after=await snapshot(s,t,task,p,req)
        loaded=await pkg.get_task(s,t.id,task.id)
        done=await pkg.complete_task(s,t.id,task.id,acting_user_id=actor.id)
        print(json.dumps({'case':'remove-one-legacy-ready-from-mixed','before':before,'after':after,'legacy_ready':loaded.lines[0].qty_legacy_confirmed_packed,'earned_kopecks':done.billing_earned_kopecks,'expected_work':1}))
    async with sf() as s:
        t,w,actor,p,req,task,box,line,locs=await fixture(s,[(0,0)],total=3)
        alloc=MarketplaceUnloadPickAllocation(request_id=req.id,product_id=p.id,storage_location_id=locs[0].id,quantity=3)
        s.add(alloc);await s.commit()
        placed=await boxes.add_manual_qty_to_box(s,t.id,box.id,product_id=p.id,storage_location_id=locs[0].id,quantity=3,actor_user_id=actor.id)
        await s.commit()
        packed_before={'box_qty':placed.quantity,'box_known':placed.quantity_source_known,'allocation_qty':alloc.quantity,'allocation_known':alloc.quantity_source_known}
        try:
            await collect.remove_from_box(s,t.id,req.id,box_id=box.id,line_id=placed.id,quantity=3,actor_user_id=actor.id)
            result='ok'
        except Exception as exc:
            result=getattr(exc,'code',type(exc).__name__);await s.rollback()
        print(json.dumps({'case':'historical-prepick-place-remove','before_remove':packed_before,'remove':result,'expected_remove':'ok'}))
    await engine.dispose()

asyncio.run(main())
